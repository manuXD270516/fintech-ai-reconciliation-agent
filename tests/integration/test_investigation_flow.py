"""M5 T08/T09: persisted investigations end to end inside the Compose network.

Real PostgreSQL + pgvector, the real fintech-mcp-server launched over stdio with the
read-only `recon_mcp` role, M3 hybrid retrieval and the deterministic scripted provider
(model output is SIMULATED; everything else is the real system).
"""

from __future__ import annotations

import asyncio
import csv
import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from sqlalchemy import func, select

from recon_agents.models import CaseSnapshot
from recon_domain.observation import SourceKind
from recon_domain.oracle import batches_for, to_csv
from recon_investigator.runner import execute
from recon_knowledge.corpus import load_corpus
from recon_knowledge.provider_status import publish_snapshots
from recon_knowledge.repository import KnowledgeRepository
from recon_store.artifacts import ArtifactService
from recon_store.engine import runtime_engine, runtime_url
from recon_store.investigations import (
    TERMINAL,
    InvestigationRepository,
    case_snapshot,
    snapshot_hash,
)
from recon_store.reconciliation import RECONCILIATION_REQUESTED, ReconciliationService
from recon_store.tables import audit_entries, outbox
from recon_worker.runner import handle_run_requested

from .support import app_connect, new_run_id, settings

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "datasets" / "synthetic" / "transactions-v2"
BATCH = "b-prov-alfa-merchant-03-USD"


@pytest.fixture(scope="module")
def world() -> Iterator[dict[str, Any]]:
    s = settings()
    engine = runtime_engine(
        runtime_url(s.db_host, s.db_port, s.db_name, s.db_user, s.db_password.get_secret_value())
    )
    tenant = f"tenant-inv-{new_run_id()}"
    files = {
        p.name: p.read_text(encoding="utf-8").replace("tenant-demo,", f"{tenant},")
        for p in DATASET.glob("*.csv")
    }
    for name, source in (("internal_ledger.csv", SourceKind.INTERNAL_LEDGER),
                         ("provider_report.csv", SourceKind.PROVIDER_REPORT)):  # fmt: skip
        rows = list(csv.DictReader(io.StringIO(files[name])))
        ArtifactService(engine).ingest(
            tenant_id=tenant, source=source, provider_id="prov-alfa", idempotency_key=name,
            content=to_csv([r for r in rows if r["provider_id"] == "prov-alfa"]),
            actor="svc-it", correlation_id="it", now=datetime.now(UTC),
        )  # fmt: skip
    labels = list(csv.DictReader(io.StringIO(files["labels.csv"])))
    batch = next(b for b in batches_for(labels) if b.batch_id == BATCH)
    service = ReconciliationService(engine)
    service.create_batch(batch, actor="ana", correlation_id="it")
    for source in batch.source_pair:
        service.mark_complete(tenant, BATCH, source, actor="svc-it", correlation_id="it")
    run_id, _ = service.request_run(tenant, BATCH, actor="ana", correlation_id="it")
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
    publish_snapshots(
        engine, ROOT / "datasets" / "synthetic" / "provider-status-v1" / "status.json"
    )
    results = {r["payment_ref"]: r for r in service.list_results(tenant, run_id, limit=500)}
    yield {"engine": engine, "tenant": tenant, "run_id": run_id, "results": results}
    engine.dispose()


async def _terminal(repo: InvestigationRepository, tenant: str, inv_id: str) -> dict[str, Any]:
    for _ in range(240):
        row = repo.get(tenant, uuid.UUID(inv_id))
        if row is not None and row["state"] in TERMINAL:
            return row
        await asyncio.sleep(0.25)
    raise AssertionError("investigation did not finish within 60 s")


def _ordinal(world: dict[str, Any], status: str, discrepancy: str | None) -> int:
    for row in world["results"].values():
        types = list(row["discrepancy_types"])
        if row["match_status"] == status and (discrepancy in types if discrepancy else not types):
            return int(row["ordinal"])
    raise AssertionError(f"no {status}/{discrepancy} result in the batch")


def test_snapshot_hash_is_shared_by_store_and_agent(world: dict[str, Any]) -> None:
    ordinal = _ordinal(world, "UNMATCHED", "AMOUNT_MISMATCH")
    snap = case_snapshot(world["engine"], world["tenant"], world["run_id"], ordinal)
    assert CaseSnapshot.from_dict(snap).snapshot_hash == snapshot_hash(snap)
    assert snap["left_transaction_ids"] and snap["right_transaction_ids"]


async def test_amount_mismatch_investigation_end_to_end(world: dict[str, Any]) -> None:
    engine, tenant = world["engine"], world["tenant"]
    repo = InvestigationRepository(engine)
    ordinal = _ordinal(world, "UNMATCHED", "AMOUNT_MISMATCH")
    inv_id, created = repo.request(
        tenant, world["run_id"], ordinal, actor="ana", correlation_id="it"
    )
    again, created_again = repo.request(
        tenant, world["run_id"], ordinal, actor="ana", correlation_id="it"
    )
    assert created and not created_again and again == inv_id
    with engine.connect() as conn:
        mcp_audits_before = conn.execute(
            select(func.count()).select_from(audit_entries).where(
                audit_entries.c.actor == "svc-investigator", audit_entries.c.tenant_id == tenant
            )
        ).scalar_one()  # fmt: skip
    # The Compose `investigator` service also receives the event (at-least-once): exactly one
    # of the two executions wins the claim; the other reports a duplicate.
    state = await execute(engine, uuid.UUID(inv_id))
    assert state in {"DRAFTED", "duplicate"}
    row = await _terminal(repo, tenant, inv_id)
    assert row["state"] == "DRAFTED"
    assert await execute(engine, uuid.UUID(inv_id)) == "duplicate"
    record = row["record"]
    draft = record["draft"]
    assert draft["operational_effect"] == "none" and draft["label"] == "SIMULATED"
    assert record["budget"]["tool_calls"] <= 6 and record["budget"]["generative_calls"] == 2
    assert {s["tool"] for s in record["steps"]} <= {
        "get_transaction", "search_provider_docs", "search_incidents", "get_provider_status",
    }  # fmt: skip
    facts = " ".join(f["statement"] for f in draft["facts"])
    assert "-100" in facts  # the provider reported 100 minor units less
    assert all(h["kind"] == "HYPOTHESIS" for h in draft["hypotheses"])
    assert draft["inferences"] == []  # 100 is not 1% of the ledger amount: no fee inference
    assert any(c["ref"].startswith("doc:") for c in draft["citations"]) or draft["hypotheses"]
    assert row["record"]["snapshot"]["case_ref"] == row["case_ref"]
    with engine.connect() as conn:
        mcp_audits_after = conn.execute(
            select(func.count()).select_from(audit_entries).where(
                audit_entries.c.actor == "svc-investigator", audit_entries.c.tenant_id == tenant
            )
        ).scalar_one()  # fmt: skip
        finish = conn.execute(
            select(audit_entries.c.outcome).where(
                audit_entries.c.action == "investigation.finish",
                audit_entries.c.resource_id == inv_id,
            )
        ).scalar_one()
    # MCP calls are audited under the server identity (+1 for the finish entry).
    assert mcp_audits_after - mcp_audits_before == record["budget"]["tool_calls"] + 1
    assert finish == "drafted"


async def test_exact_result_needs_no_investigation(world: dict[str, Any]) -> None:
    repo = InvestigationRepository(world["engine"])
    ordinal = _ordinal(world, "EXACT", None)
    inv_id, _ = repo.request(world["tenant"], world["run_id"], ordinal, actor="ana",
                             correlation_id="it")  # fmt: skip
    assert await execute(world["engine"], uuid.UUID(inv_id)) in {"NOT_NEEDED", "duplicate"}
    row = await _terminal(repo, world["tenant"], inv_id)
    assert row["state"] == "NOT_NEEDED"
    assert row["record"]["budget"]["tool_calls"] == 0
    assert row["record"]["budget"]["generative_calls"] == 0


def test_other_tenant_cannot_read_investigations(world: dict[str, Any]) -> None:
    repo = InvestigationRepository(world["engine"])
    ordinal = _ordinal(world, "UNMATCHED", "AMOUNT_MISMATCH")
    inv_id, _ = repo.request(world["tenant"], world["run_id"], ordinal, actor="ana",
                             correlation_id="it")  # fmt: skip
    assert repo.get("tenant-intruder", uuid.UUID(inv_id)) is None
    with pytest.raises(LookupError):
        repo.request("tenant-intruder", world["run_id"], ordinal, actor="x", correlation_id="it")


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM recon.investigations WHERE false",
        "UPDATE recon.investigations SET requested_by = 'x' WHERE false",
        "UPDATE recon.investigations SET input_snapshot_hash = 'x' WHERE false",
    ],
)
def test_runtime_role_cannot_rewrite_investigation_identity(statement: str) -> None:
    with app_connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)
