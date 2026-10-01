"""M4 T07/T08: fintech-mcp-server over real stdio with the SQL backend and the read-only
`recon_mcp` database role (PostgreSQL + pgvector inside the Compose network).
"""

from __future__ import annotations

import csv
import io
import os
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from sqlalchemy import Engine, func, select

from recon_domain.observation import SourceKind
from recon_domain.oracle import batches_for, to_csv
from recon_knowledge.corpus import load_corpus
from recon_knowledge.provider_status import publish_snapshots
from recon_knowledge.repository import KnowledgeRepository
from recon_mcp.contracts import PROTOCOL_VERSION, Scope
from recon_store.artifacts import ArtifactService
from recon_store.engine import runtime_engine, runtime_url
from recon_store.observations import transaction_uid
from recon_store.reconciliation import RECONCILIATION_REQUESTED, ReconciliationService
from recon_store.tables import audit_entries, observations, outbox
from recon_worker.runner import handle_run_requested

from .support import new_run_id, settings

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "datasets" / "synthetic" / "transactions-v2"


@pytest.fixture(scope="module")
def world() -> Iterator[dict[str, Any]]:
    """A fresh tenant with ingested v2 data, one completed run per batch and knowledge."""
    s = settings()
    engine = runtime_engine(
        runtime_url(s.db_host, s.db_port, s.db_name, s.db_user, s.db_password.get_secret_value())
    )
    tenant = f"tenant-mcp-{new_run_id()}"
    files = {
        p.name: p.read_text(encoding="utf-8").replace("tenant-demo,", f"{tenant},")
        for p in DATASET.glob("*.csv")
    }
    artifacts = ArtifactService(engine)
    for name, source in (("internal_ledger.csv", SourceKind.INTERNAL_LEDGER),
                         ("provider_report.csv", SourceKind.PROVIDER_REPORT)):  # fmt: skip
        rows = list(csv.DictReader(io.StringIO(files[name])))
        for provider in ("prov-alfa", "prov-beta"):
            artifacts.ingest(
                tenant_id=tenant, source=source, provider_id=provider,
                idempotency_key=f"{name}-{provider}",
                content=to_csv([r for r in rows if r["provider_id"] == provider]),
                actor="svc-it", correlation_id="it", now=datetime.now(UTC),
            )  # fmt: skip
    service = ReconciliationService(engine)
    labels = list(csv.DictReader(io.StringIO(files["labels.csv"])))
    batch = batches_for(labels)[0]
    service.create_batch(batch, actor="ana", correlation_id="it")
    run_id, _ = service.request_run(tenant, batch.batch_id, actor="ana", correlation_id="it")
    with engine.connect() as conn:
        event_id: uuid.UUID = conn.execute(
            select(outbox.c.event_id).where(
                outbox.c.event_type == RECONCILIATION_REQUESTED,
                outbox.c.aggregate_id == f"run/{run_id}",
            )
        ).scalar_one()
    handle_run_requested(engine, {"event_id": str(event_id), "payload": {"run_id": str(run_id)}})
    repo = KnowledgeRepository(engine)
    for doc in load_corpus(ROOT / "datasets" / "synthetic" / "knowledge-v1"):
        repo.publish(doc, actor="svc-it", correlation_id="it")
    status_file = ROOT / "datasets" / "synthetic" / "provider-status-v1" / "status.json"
    publish_snapshots(engine, status_file)
    yield {"engine": engine, "tenant": tenant, "batch": batch, "run_id": str(run_id)}
    engine.dispose()


def _params(tenant: str, subject: str = "svc-investigator-it") -> StdioServerParameters:
    env = dict(os.environ) | {
        "MCP_SUBJECT": subject,
        "MCP_TENANT_ID": tenant,
        "MCP_SCOPES": ",".join(s.value for s in Scope),
    }
    return StdioServerParameters(
        command=sys.executable, args=["-m", "recon_mcp", "--backend", "sql"], env=env
    )


def _uid(tenant: str, source: str, record_id: str) -> str:
    return str(transaction_uid(tenant, source, record_id))


async def test_generated_uid_matches_python_twin(world: dict[str, Any]) -> None:
    engine: Engine = world["engine"]
    with engine.connect() as conn:
        row = conn.execute(
            select(
                observations.c.tenant_id,
                observations.c.source,
                observations.c.source_record_id,
                observations.c.transaction_uid,
            )
            .where(observations.c.tenant_id == world["tenant"])
            .limit(1)
        ).one()
    assert str(row.transaction_uid) == _uid(row.tenant_id, row.source, row.source_record_id)


async def test_sql_backend_end_to_end_over_stdio(world: dict[str, Any]) -> None:
    tenant, batch = world["tenant"], world["batch"]
    ledger = _uid(tenant, "internal_ledger", "led-000005")
    foreign = _uid("tenant-demo", "internal_ledger", "led-000005")
    engine: Engine = world["engine"]
    with engine.connect() as conn:
        audits_before = conn.execute(
            select(func.count()).select_from(audit_entries).where(
                audit_entries.c.actor == "svc-investigator-it",
                audit_entries.c.tenant_id == tenant,
            )
        ).scalar_one()  # fmt: skip
    async with Client(_params(tenant), mode="legacy") as client:
        assert client.protocol_version == PROTOCOL_VERSION
        assert len((await client.list_tools()).tools) == 6
        tx = await client.call_tool("get_transaction", {"transaction_id": ledger})
        hidden = await client.call_tool("get_transaction", {"transaction_id": foreign})
        related = await client.call_tool("find_related_transactions", {"transaction_id": ledger})
        page = await client.call_tool(
            "get_reconciliation_batch", {"batch_id": batch.batch_id, "limit": 2}
        )
        status = await client.call_tool(
            "get_provider_status",
            {"provider_id": "prov-alfa", "as_of": "2026-08-16T00:00:00+00:00"},
        )
        docs = await client.call_tool(
            "search_provider_docs",
            {"query": "captura duplicada", "provider_id": "prov-alfa", "error_code": "E17"},
        )
        incidents = await client.call_tool(
            "search_incidents", {"query": "liquidación neta inesperada", "provider_id": "prov-alfa"}
        )
    assert not tx.is_error and tx.structured_content["data"]["source_record_id"] == "led-000005"
    assert hidden.is_error and hidden.structured_content["error"]["code"] == "NOT_FOUND"
    payment_ref = tx.structured_content["data"]["payment_ref"]
    candidates = related.structured_content["data"]["candidates"]
    assert any(
        c["payment_ref"] == payment_ref and "same_reference" in c["relations"] for c in candidates
    )
    data = page.structured_content["data"]
    assert data["run"]["run_id"] == world["run_id"] and data["run"]["status"] == "completed"
    assert len(data["results"]) == 2 and page.structured_content["next_cursor"]
    sources = {t["source"] for t in data["totals_by_currency"]}
    assert sources <= {"internal_ledger", "provider_report"}
    assert status.structured_content["data"]["snapshot"]["status"] == "degraded"
    first = docs.structured_content["data"]["items"][0]
    assert first["document_id"] == "alfa-error-codes" and first["version"] == 2
    assert first["citation"].startswith("[alfa-error-codes@2#")
    assert {i["document_type"] for i in incidents.structured_content["data"]["items"]} == {
        "incident"
    }
    with engine.connect() as conn:
        audits_after = conn.execute(
            select(func.count()).select_from(audit_entries).where(
                audit_entries.c.actor == "svc-investigator-it",
                audit_entries.c.tenant_id == tenant,
            )
        ).scalar_one()  # fmt: skip
    assert audits_after - audits_before == 7


def _mcp_connect() -> psycopg.Connection[tuple[object, ...]]:
    s = settings()
    return psycopg.connect(
        host=os.environ["MCP_DB_HOST"],
        port=int(os.environ.get("MCP_DB_PORT", "5432")),
        dbname=s.db_name,
        user=os.environ["MCP_DB_USER"],
        password=os.environ["MCP_DB_PASSWORD"],
        autocommit=True,
        connect_timeout=5,
    )


def test_mcp_role_reads_evidence() -> None:
    with _mcp_connect() as conn:
        assert conn.execute("SELECT count(*) FROM recon.knowledge_chunks").fetchone() is not None
        attrs = conn.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
    assert attrs == (False, False, False)


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO recon.reconciliation_batches (tenant_id) VALUES ('x')",
        "UPDATE recon.match_results SET match_status = 'EXACT' WHERE false",
        "DELETE FROM recon.transaction_observations WHERE false",
        "UPDATE recon.knowledge_documents SET review_status = 'revoked' WHERE false",
        "DELETE FROM recon.audit_entries WHERE false",
        "UPDATE recon.audit_entries SET outcome = 'x' WHERE false",
        "SELECT * FROM recon.outbox LIMIT 1",
        "SELECT * FROM recon.source_artifacts LIMIT 1",
        "CREATE TABLE recon.intruder (id int)",
    ],
)
def test_mcp_role_cannot_write_or_read_beyond_evidence(statement: str) -> None:
    with _mcp_connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)


def test_unique_tenant_ids_do_not_collide() -> None:
    assert _uid("a", "internal_ledger", "x") != _uid("b", "internal_ledger", "x")
    assert uuid.UUID(_uid("a", "internal_ledger", "x"))
