"""M2 T04/T07: event ingestion through the running worker, DLQ and late arrivals (RC10).

Runs inside the smoke container: publishes to the real JetStream and waits for the
Compose `worker` service to persist the effects in PostgreSQL.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from recon_domain.batch import ReconciliationBatch
from recon_domain.observation import SourceKind
from recon_domain.oracle import to_csv
from recon_store.artifacts import ArtifactService
from recon_store.engine import runtime_engine, runtime_url
from recon_store.reconciliation import RECONCILIATION_REQUESTED, ReconciliationService
from recon_store.tables import artifacts, outbox, rejections
from recon_worker.runner import (
    DLQ_PREFIX,
    DLQ_STREAM,
    INGEST_CONSUMER,
    handle_run_requested,
    ingest_subject,
)

from .support import nats_connect, new_run_id, settings

pytestmark = pytest.mark.integration
DATASET = Path(__file__).resolve().parents[2] / "datasets" / "synthetic" / "transactions-v2"


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    s = settings()
    eng = runtime_engine(
        runtime_url(s.db_host, s.db_port, s.db_name, s.db_user, s.db_password.get_secret_value())
    )
    yield eng
    eng.dispose()


def _provider_rows(tenant: str) -> list[dict[str, str]]:
    text = (DATASET / "provider_report.csv").read_text(encoding="utf-8")
    rows = [dict(r, tenant_id=tenant) for r in csv.DictReader(io.StringIO(text))]
    return [r for r in rows if r["provider_id"] == "prov-alfa"]


def _artifact_count(engine: Engine, tenant: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                select(func.count()).select_from(artifacts).where(artifacts.c.tenant_id == tenant)
            ).scalar_one()
        )


async def _wait(predicate: Callable[[], bool], limit: float = 30) -> None:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if await asyncio.to_thread(predicate):
            return
        await asyncio.sleep(0.25)
    raise AssertionError("condition not reached within timeout")


async def test_events_are_ingested_once_by_the_worker(engine: Engine) -> None:
    tenant = f"tenant-ev-{new_run_id()}"
    rows = _provider_rows(tenant)[:6]
    subject = ingest_subject(tenant, SourceKind.PROVIDER_REPORT, "prov-alfa")
    events = [{"event_id": str(uuid.uuid4()), "record": row} for row in rows]
    nc = await nats_connect()
    try:
        js = nc.jetstream()
        for event in events + events[:2]:  # the last two are redeliveries (same event_id)
            await js.publish(subject, json.dumps(event).encode(), timeout=5)
        await _wait(lambda: _artifact_count(engine, tenant) == len(events))
        await asyncio.sleep(1.5)
        assert _artifact_count(engine, tenant) == len(events)
    finally:
        await nc.drain()
    with engine.connect() as conn:
        keys = conn.execute(
            select(artifacts.c.idempotency_key, artifacts.c.received_by).where(
                artifacts.c.tenant_id == tenant
            )
        ).all()
    assert {k for k, _ in keys} == {f"evt-{e['event_id']}" for e in events}
    assert {actor for _, actor in keys} == {"svc-ingest-provider_report"}


async def test_body_cannot_override_subject_tenant(engine: Engine) -> None:
    tenant = f"tenant-ev-{new_run_id()}"
    row = dict(_provider_rows(tenant)[0], tenant_id="tenant-victim")
    nc = await nats_connect()
    try:
        await nc.jetstream().publish(
            ingest_subject(tenant, SourceKind.PROVIDER_REPORT, "prov-alfa"),
            json.dumps({"event_id": str(uuid.uuid4()), "record": row}).encode(),
            timeout=5,
        )
        await _wait(lambda: _artifact_count(engine, tenant) == 1)
    finally:
        await nc.drain()
    with engine.connect() as conn:
        stmt = select(rejections.c.code).where(rejections.c.tenant_id == tenant)
        codes = [str(row[0]) for row in conn.execute(stmt)]
        assert codes == ["scope_violation"]


async def test_poison_event_goes_to_dead_letter_stream() -> None:
    marker = f"poison-{new_run_id()}"
    nc = await nats_connect()
    try:
        js = nc.jetstream()
        await js.publish(
            ingest_subject("tenant-demo", SourceKind.PROVIDER_REPORT, "prov-alfa"),
            json.dumps({"event_id": marker, "record": {}}).encode(),
            timeout=5,
        )
        sub = await js.pull_subscribe(
            f"{DLQ_PREFIX}.{INGEST_CONSUMER}", durable=f"it-{marker}", stream=DLQ_STREAM
        )
        found = None
        deadline = time.monotonic() + 30
        while found is None and time.monotonic() < deadline:
            try:
                for msg in await sub.fetch(batch=50, timeout=1):
                    await msg.ack()
                    if marker in msg.data.decode():
                        found = json.loads(msg.data)
            except TimeoutError:
                continue
        await js.delete_consumer(DLQ_STREAM, f"it-{marker}")
    finally:
        await nc.drain()
    assert found is not None
    assert found["reason"].startswith("poison:")


def test_rc10_late_arrival_creates_new_run_and_keeps_previous(engine: Engine) -> None:
    tenant = f"tenant-late-{new_run_id()}"
    first_row = _provider_rows(tenant)[0]
    scope = {"merchant_account": first_row["merchant_account"], "currency": "USD",
             "status": "SETTLED"}  # fmt: skip
    rows = [dict(r, **scope) for r in _provider_rows(tenant)[:3]]
    ledger = [dict(r, source_record_id=f"led-{i}", operation="CAPTURE", status="POSTED")
              for i, r in enumerate(rows[:3])]  # fmt: skip
    service, ingest = ReconciliationService(engine), ArtifactService(engine)
    now = datetime.now(UTC)
    for key, source, content in (
        ("ledger", SourceKind.INTERNAL_LEDGER, to_csv(ledger)),
        ("provider-1", SourceKind.PROVIDER_REPORT, to_csv([rows[0], rows[1]])),
    ):
        ingest.ingest(tenant_id=tenant, source=source, provider_id="prov-alfa",
                      idempotency_key=key, content=content, actor="svc-it",
                      correlation_id="it", now=now)  # fmt: skip
    start = datetime(2026, 9, 1, 4, tzinfo=UTC)
    batch = ReconciliationBatch(
        tenant_id=tenant, batch_id="late", provider_id="prov-alfa",
        merchant_account=rows[0]["merchant_account"], currency="USD",
        window_start=start, window_end=start + timedelta(days=2),
        business_timezone="America/La_Paz",
        source_pair=(SourceKind.INTERNAL_LEDGER, SourceKind.PROVIDER_REPORT),
        cutoff_at=start + timedelta(days=2),
    )  # fmt: skip
    service.create_batch(batch, actor="ana", correlation_id="it")

    def run() -> uuid.UUID:
        run_id, _ = service.request_run(tenant, "late", actor="ana", correlation_id="it")
        with engine.connect() as conn:
            event_id: uuid.UUID = conn.execute(
                select(outbox.c.event_id).where(
                    outbox.c.event_type == RECONCILIATION_REQUESTED,
                    outbox.c.aggregate_id == f"run/{run_id}",
                )
            ).scalar_one()
        handle_run_requested(
            engine, {"event_id": str(event_id), "payload": {"run_id": str(run_id)}}
        )
        return run_id

    first = run()
    before = service.list_results(tenant, first, limit=500)
    ingest.ingest(tenant_id=tenant, source=SourceKind.PROVIDER_REPORT, provider_id="prov-alfa",
                  idempotency_key="provider-late", content=to_csv([rows[2]]), actor="svc-it",
                  correlation_id="it", now=now)  # fmt: skip
    second = run()
    r1, r2 = service.get_run(tenant, first), service.get_run(tenant, second)
    assert (r1["run_number"], r2["run_number"]) == (1, 2)
    assert r1["snapshot_hash"] != r2["snapshot_hash"]
    assert service.list_results(tenant, first, limit=500) == before
    assert service.status_counts(second).get("EXACT", 0) > service.status_counts(first).get(
        "EXACT", 0
    )
