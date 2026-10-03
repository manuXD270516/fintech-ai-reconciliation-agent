"""M6 T04-T07: cases, recommendations and human decisions on real PostgreSQL.

HU01 (self-approval denied and audited), HU02 (concurrent decisions: one transition),
stale versions, expiry, obsolescence by a newer run (RC10), atomic audit/outbox and the
reconstructed audit trail (UC08). Approval never executes money movement.
"""

from __future__ import annotations

import asyncio
import csv
import io
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from sqlalchemy import Engine, func, select

from recon_domain.approval import Action, Decision
from recon_domain.observation import SourceKind
from recon_domain.oracle import batches_for, to_csv
from recon_investigator.runner import execute
from recon_knowledge.corpus import load_corpus
from recon_knowledge.provider_status import publish_snapshots
from recon_knowledge.repository import KnowledgeRepository
from recon_store.artifacts import ArtifactService
from recon_store.cases import APPROVAL_RECORDED, CaseError, CaseService
from recon_store.engine import runtime_engine, runtime_url
from recon_store.investigations import TERMINAL, InvestigationRepository
from recon_store.reconciliation import RECONCILIATION_REQUESTED, ReconciliationService
from recon_store.tables import audit_entries, decisions, outbox, recommendations
from recon_worker.runner import handle_run_requested

from .support import app_connect, new_run_id, settings

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "datasets" / "synthetic" / "transactions-v2"
BATCH = "b-prov-alfa-merchant-03-USD"
SUP = frozenset({"supervisor"})
NOW = datetime.now(UTC)


def _run(engine: Engine, tenant: str) -> uuid.UUID:
    service = ReconciliationService(engine)
    run_id, _ = service.request_run(tenant, BATCH, actor="ana", correlation_id="it")
    with engine.connect() as conn:
        event_id: uuid.UUID = conn.execute(
            select(outbox.c.event_id).where(
                outbox.c.event_type == RECONCILIATION_REQUESTED,
                outbox.c.aggregate_id == f"run/{run_id}",
            )
        ).scalar_one()
    handle_run_requested(engine, {"event_id": str(event_id), "payload": {"run_id": str(run_id)}})
    return run_id


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    s = settings()
    eng = runtime_engine(
        runtime_url(s.db_host, s.db_port, s.db_name, s.db_user, s.db_password.get_secret_value())
    )
    repo = KnowledgeRepository(eng)
    for doc in load_corpus(ROOT / "datasets" / "synthetic" / "knowledge-v1"):
        repo.publish(doc, actor="svc-it", correlation_id="it")
    publish_snapshots(eng, ROOT / "datasets" / "synthetic" / "provider-status-v1" / "status.json")
    yield eng
    eng.dispose()


def _world(engine: Engine) -> dict[str, Any]:
    """A fresh tenant per test: v2 data, one completed run, the mismatch result ordinal."""
    tenant = f"tenant-case-{new_run_id()}"
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
            actor="svc-it", correlation_id="it", now=NOW,
        )  # fmt: skip
    labels = list(csv.DictReader(io.StringIO(files["labels.csv"])))
    batch = next(b for b in batches_for(labels) if b.batch_id == BATCH)
    service = ReconciliationService(engine)
    service.create_batch(batch, actor="ana", correlation_id="it")
    for source in batch.source_pair:
        service.mark_complete(tenant, BATCH, source, actor="svc-it", correlation_id="it")
    run_id = _run(engine, tenant)
    found = service.list_results(tenant, run_id, limit=500)
    mismatch = next(r for r in found if "AMOUNT_MISMATCH" in r["discrepancy_types"])
    exact = next(r for r in found if r["match_status"] == "EXACT")
    return {"tenant": tenant, "run_id": run_id, "ordinal": mismatch["ordinal"],
            "exact": exact["ordinal"]}  # fmt: skip


async def _investigate(engine: Engine, w: dict[str, Any], ordinal: int) -> uuid.UUID:
    repo = InvestigationRepository(engine)
    inv_id, _ = repo.request(w["tenant"], w["run_id"], ordinal, actor="luis", correlation_id="it")
    await execute(engine, uuid.UUID(inv_id))
    for _ in range(240):
        row = repo.get(w["tenant"], uuid.UUID(inv_id))
        if row is not None and row["state"] in TERMINAL:
            return uuid.UUID(inv_id)
        await asyncio.sleep(0.25)
    raise AssertionError("investigation did not finish")


def _proposed(engine: Engine, w: dict[str, Any], inv: uuid.UUID | None = None,
              now: datetime = NOW) -> tuple[CaseService, uuid.UUID, uuid.UUID]:  # fmt: skip
    cases = CaseService(engine)
    case_id, created = cases.open(w["tenant"], w["run_id"], w["ordinal"], actor="ana",
                                  correlation_id="it")  # fmt: skip
    assert created
    assert cases.open(w["tenant"], w["run_id"], w["ordinal"], actor="ana",
                      correlation_id="it") == (case_id, False)  # fmt: skip
    rec = cases.propose(w["tenant"], case_id, actor="ana", action=Action.REQUEST_PROVIDER_INFO,
                        rationale="pedir al proveedor el reporte corregido", expected_version=1,
                        investigation_id=inv, correlation_id="it", now=now)  # fmt: skip
    return cases, case_id, rec


def _decide(cases: CaseService, w: dict[str, Any], case_id: uuid.UUID, rec: uuid.UUID,
            actor: str = "sofia", key: str | None = None, version: int = 2,
            reason: str = "aprobado: solicitar información al proveedor",
            decision: Decision = Decision.APPROVE) -> tuple[dict[str, Any], bool]:  # fmt: skip
    return cases.decide(w["tenant"], case_id, actor=actor, roles=SUP, recommendation_id=rec,
                        decision=decision, reason=reason, expected_version=version,
                        idempotency_key=key or f"k-{uuid.uuid4().hex[:8]}",
                        correlation_id="it", now=datetime.now(UTC))  # fmt: skip


async def test_reviewed_draft_to_human_decision_and_audit_trail(engine: Engine) -> None:
    w = _world(engine)
    inv = await _investigate(engine, w, w["ordinal"])
    cases, case_id, rec = _proposed(engine, w, inv)
    row, replayed = _decide(cases, w, case_id, rec, key="decision-1")
    assert not replayed and row["case_version"] == 2
    again, replayed = _decide(cases, w, case_id, rec, key="decision-1")
    assert replayed and again["id"] == row["id"]
    with pytest.raises(CaseError) as reused:
        _decide(cases, w, case_id, rec, key="decision-1", reason="otro motivo distinto aquí")
    assert reused.value.code == "idempotency_conflict"
    state = cases.get(w["tenant"], case_id)
    assert (state["status"], state["version"]) == ("APPROVED", 3)
    assert state["recommendations"][0]["review_result"] == "SUPPORTED"
    assert state["recommendations"][0]["evidence"]["citations"]
    assert cases.close(w["tenant"], case_id, actor="sofia", roles=SUP,
                       reason="información solicitada; sin ajuste", expected_version=3,
                       correlation_id="it") == 4  # fmt: skip
    trail = cases.audit_trail(w["tenant"], case_id, actor="auditor-1", correlation_id="it")
    actions = [e["action"] for e in trail["audit"]]
    for action in ("case.open", "recommendation.create", "decision.record", "case.close",
                   "investigation.request", "investigation.finish"):  # fmt: skip
        assert action in actions, action
    assert trail["rules"]["ruleset_version"] == "rules/v1" and trail["rules"]["snapshot_hash"]
    [investigation] = trail["investigations"]
    assert investigation["steps"] and investigation["citations"]
    assert investigation["review"]["result"] == "SUPPORTED"
    with engine.connect() as conn:
        events: list[Any] = conn.execute(  # type: ignore[assignment]
            select(outbox.c.payload).where(
                outbox.c.event_type == APPROVAL_RECORDED, outbox.c.aggregate_id == f"case/{case_id}"
            )
        ).scalars().all()  # fmt: skip
    assert len(events) == 1 and events[0]["operational_effect"].startswith("none")


def test_hu01_self_approval_is_denied_and_audited(engine: Engine) -> None:
    w = _world(engine)
    cases, case_id, rec = _proposed(engine, w)
    with pytest.raises(CaseError) as denied:
        _decide(cases, w, case_id, rec, actor="ana")
    assert denied.value.code == "segregation_of_duties"
    assert cases.get(w["tenant"], case_id)["status"] == "HUMAN_REVIEW"
    with engine.connect() as conn:
        outcome: str = conn.execute(
            select(audit_entries.c.outcome).where(
                audit_entries.c.action == "decision.denied",
                audit_entries.c.resource_id == str(case_id),
                audit_entries.c.actor == "ana",
            )
        ).scalar_one()
    assert outcome == "segregation_of_duties"


def test_hu02_concurrent_decisions_produce_one_transition(engine: Engine) -> None:
    w = _world(engine)
    cases, case_id, rec = _proposed(engine, w)
    outcomes: list[str] = []
    barrier = threading.Barrier(4)

    def attempt(actor: str) -> None:
        barrier.wait()
        try:
            _decide(cases, w, case_id, rec, actor=actor)
            outcomes.append("ok")
        except CaseError as exc:
            outcomes.append(exc.code)

    threads = [threading.Thread(target=attempt, args=(f"sup-{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count("ok") == 1
    assert set(outcomes) - {"ok"} <= {"version_conflict", "case_status_not_allowed",
                                      "recommendation_not_pending"}  # fmt: skip
    with engine.connect() as conn:
        count = conn.execute(
            select(func.count()).select_from(decisions).where(decisions.c.case_id == case_id)
        ).scalar_one()
    assert count == 1


@pytest.mark.parametrize("decision", list(Decision))
def test_every_decision_is_persisted(engine: Engine, decision: Decision) -> None:
    # Regression: NEEDS_INFORMATION (17 chars) overflowed recommendations.status (16).
    w = _world(engine)
    cases, case_id, rec = _proposed(engine, w)
    row, replayed = _decide(cases, w, case_id, rec, decision=decision,
                            reason=f"decisión {decision.value} sobre la propuesta")  # fmt: skip
    assert not replayed and row["decision"] == decision.value
    state = cases.get(w["tenant"], case_id)
    assert state["status"] == state["recommendations"][0]["status"]
    assert state["status"] in {"APPROVED", "REJECTED", "NEEDS_INFORMATION"}


def test_stale_version_and_expired_recommendation(engine: Engine) -> None:
    w = _world(engine)
    cases, case_id, rec = _proposed(engine, w, now=NOW - timedelta(days=4))
    with pytest.raises(CaseError) as stale:
        _decide(cases, w, case_id, rec, version=1)
    assert stale.value.code == "version_conflict"
    with pytest.raises(CaseError) as expired:
        _decide(cases, w, case_id, rec)
    assert expired.value.code == "recommendation_expired"


def test_rc10_newer_run_makes_the_recommendation_obsolete(engine: Engine) -> None:
    w = _world(engine)
    cases, case_id, rec = _proposed(engine, w)
    _run(engine, w["tenant"])  # late evidence -> a newer run of the same batch
    with pytest.raises(CaseError) as obsolete:
        _decide(cases, w, case_id, rec)
    assert obsolete.value.code == "recommendation_obsolete"
    with engine.connect() as conn:
        status: str = conn.execute(
            select(recommendations.c.status).where(recommendations.c.id == rec)
        ).scalar_one()
    assert status == "OBSOLETE"


async def test_unreviewed_or_unneeded_drafts_cannot_be_adopted(engine: Engine) -> None:
    w = _world(engine)
    not_needed = await _investigate(engine, w, w["exact"])
    cases = CaseService(engine)
    case_id, _ = cases.open(w["tenant"], w["run_id"], w["ordinal"], actor="ana",
                            correlation_id="it")  # fmt: skip
    with pytest.raises(CaseError) as refused:
        cases.propose(w["tenant"], case_id, actor="ana", action=Action.CLOSE_AS_EXPLAINED,
                      rationale="explicado por el borrador", expected_version=1,
                      investigation_id=not_needed, correlation_id="it", now=NOW)  # fmt: skip
    assert refused.value.code == "not_found"  # the draft belongs to another result


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE recon.decisions SET decision = 'REJECT' WHERE false",
        "DELETE FROM recon.decisions WHERE false",
        "UPDATE recon.recommendations SET rationale = 'x' WHERE false",
        "UPDATE recon.cases SET opened_by = 'x' WHERE false",
        "DELETE FROM recon.cases WHERE false",
    ],
)
def test_runtime_role_cannot_rewrite_decisions(statement: str) -> None:
    with app_connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)
