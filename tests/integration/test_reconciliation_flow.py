"""M2 T04/T07: persisted ingestion + reconciliation against real PostgreSQL (smoke container).

The v2 dataset is ingested under a unique tenant, runs are requested through the outbox
path and executed by the worker handler; results must equal the oracle labels.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from recon_domain.observation import SourceKind
from recon_domain.oracle import batches_for, expected, to_csv
from recon_store.artifacts import ArtifactService, IdempotencyConflictError, Receipt
from recon_store.engine import runtime_engine, runtime_url
from recon_store.reconciliation import (
    RECONCILIATION_REQUESTED,
    NotFoundError,
    ReconciliationService,
)
from recon_store.tables import outbox, runs
from recon_worker.runner import handle_run_requested

from .support import new_run_id, settings

pytestmark = pytest.mark.integration
DATASET = Path(__file__).resolve().parents[2] / "datasets" / "synthetic" / "transactions-v2"
SOURCES = {"internal_ledger.csv": SourceKind.INTERNAL_LEDGER,
           "provider_report.csv": SourceKind.PROVIDER_REPORT}  # fmt: skip


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    s = settings()
    eng = runtime_engine(
        runtime_url(s.db_host, s.db_port, s.db_name, s.db_user, s.db_password.get_secret_value())
    )
    yield eng
    eng.dispose()


def _files(tenant: str) -> dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8").replace("tenant-demo,", f"{tenant},")
        for p in DATASET.glob("*.csv")
    }


def _ingest_all(service: ArtifactService, files: dict[str, str], tenant: str) -> list[Receipt]:
    receipts = []
    for name, source in SOURCES.items():
        rows = list(csv.DictReader(io.StringIO(files[name])))
        for provider in ("prov-alfa", "prov-beta"):
            content = to_csv([r for r in rows if r["provider_id"] == provider])
            receipts.append(
                service.ingest(
                    tenant_id=tenant, source=source, provider_id=provider,
                    idempotency_key=f"{name}-{provider}", content=content, actor="svc-it",
                    correlation_id="it-ingest", now=datetime.now(UTC),
                )
            )  # fmt: skip
    return receipts


def _run_event(engine: Engine, run_id: uuid.UUID) -> dict[str, object]:
    with engine.connect() as conn:
        row = conn.execute(
            select(outbox).where(
                outbox.c.event_type == RECONCILIATION_REQUESTED,
                outbox.c.aggregate_id == f"run/{run_id}",
            )
        ).mappings().one()  # fmt: skip
    return {"event_id": str(row["event_id"]), "payload": row["payload"]}


def test_dataset_end_to_end_matches_oracle(engine: Engine) -> None:
    tenant = f"tenant-it-{new_run_id()}"
    files = _files(tenant)
    artifacts = ArtifactService(engine)
    receipts = _ingest_all(artifacts, files, tenant)
    assert sum(r.rejected for r in receipts) == 8
    assert sum(r.duplicates for r in receipts) == 4

    replay = _ingest_all(artifacts, files, tenant)
    assert all(r.replayed for r in replay)

    service = ReconciliationService(engine)
    labels = list(csv.DictReader(io.StringIO(files["labels.csv"])))
    got: dict[str, tuple[str, str]] = {}
    for batch in batches_for(labels):
        service.create_batch(batch, actor="ana", correlation_id="it")
        for source in batch.source_pair:
            service.mark_complete(tenant, batch.batch_id, source, actor="svc-it",
                                  correlation_id="it")  # fmt: skip
        run_id, number = service.request_run(tenant, batch.batch_id, actor="ana",
                                             correlation_id="it")  # fmt: skip
        assert number == 1
        event = _run_event(engine, run_id)
        assert handle_run_requested(engine, event) == "processed"
        assert handle_run_requested(engine, event) == "duplicate"
        assert service.get_run(tenant, run_id)["status"] == "completed"
        for row in service.list_results(tenant, run_id, limit=500):
            got[row["payment_ref"]] = (row["match_status"], ",".join(row["discrepancy_types"]))

    want = {ref: (c.match_status, c.discrepancies) for ref, c in expected(files).items()}
    assert got == want


def test_rerun_creates_new_version_and_keeps_previous(engine: Engine) -> None:
    tenant = f"tenant-it-{new_run_id()}"
    files = _files(tenant)
    _ingest_all(ArtifactService(engine), files, tenant)
    service = ReconciliationService(engine)
    batch = batches_for(list(csv.DictReader(io.StringIO(files["labels.csv"]))))[0]
    service.create_batch(batch, actor="ana", correlation_id="it")
    first, _ = service.request_run(tenant, batch.batch_id, actor="ana", correlation_id="it")
    handle_run_requested(engine, _run_event(engine, first))
    second, number = service.request_run(tenant, batch.batch_id, actor="ana", correlation_id="it")
    handle_run_requested(engine, _run_event(engine, second))
    assert number == 2
    with engine.connect() as conn:
        rows = conn.execute(
            select(runs.c.run_number, runs.c.snapshot_hash).where(runs.c.batch_id == batch.batch_id,
                                                                  runs.c.tenant_id == tenant)
        ).all()  # fmt: skip
    assert sorted(r[0] for r in rows) == [1, 2]
    assert len({r[1] for r in rows}) == 1
    assert service.list_results(tenant, first) == service.list_results(tenant, first)


def test_idempotency_key_reuse_with_other_content_conflicts(engine: Engine) -> None:
    tenant = f"tenant-it-{new_run_id()}"
    service = ArtifactService(engine)
    content = _files(tenant)["provider_report.csv"]
    kwargs = {"tenant_id": tenant, "source": SourceKind.PROVIDER_REPORT, "provider_id": "prov-alfa",
              "idempotency_key": "same-key", "actor": "svc-it", "correlation_id": "it",
              "now": datetime.now(UTC)}  # fmt: skip
    service.ingest(content=content, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(IdempotencyConflictError):
        service.ingest(content=content + "\n", **kwargs)  # type: ignore[arg-type]


def test_tenant_isolation_on_reads(engine: Engine) -> None:
    tenant = f"tenant-it-{new_run_id()}"
    files = _files(tenant)
    service = ReconciliationService(engine)
    batch = batches_for(list(csv.DictReader(io.StringIO(files["labels.csv"]))))[0]
    service.create_batch(batch, actor="ana", correlation_id="it")
    run_id, _ = service.request_run(tenant, batch.batch_id, actor="ana", correlation_id="it")
    with pytest.raises(NotFoundError):
        service.get_run("tenant-intruder", run_id)
    with pytest.raises(NotFoundError):
        service.get_batch("tenant-intruder", batch.batch_id)
