"""M2 T02/T03/T05: seed-catalog cases (docs/07-evals.md RC01-RC13) not covered elsewhere,
a larger deterministic benchmark and the event-ingestion guards of the worker.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from recon_domain.batch import ReconciliationBatch
from recon_domain.money import Money
from recon_domain.observation import DualTime, OperationType, SourceKind
from recon_domain.oracle import expected, run_files
from recon_domain.reconciliation import (
    DiscrepancyType,
    MatchStatus,
    Outcome,
    RunInput,
    SnapshotItem,
    reconcile,
)
from recon_domain.synthetic import generate
from recon_worker.runner import (
    PoisonMessageError,
    handle_observation_event,
    handle_run_requested,
    ingest_subject,
    parse_ingest_subject,
)

from .domain_support import observation

ROOT = Path(__file__).resolve().parents[2]
START = datetime(2026, 9, 1, 4, 0, tzinfo=UTC)
AFTER_CUTOFF = START + timedelta(days=3)
COMPLETE = {SourceKind.INTERNAL_LEDGER: True, SourceKind.PROVIDER_REPORT: True}
LEDGER = observation()
PROVIDER = observation(
    source=SourceKind.PROVIDER_REPORT, source_record_id="alf-1", attempt_ref=None
)


def _batch(currency: str = "USD") -> ReconciliationBatch:
    return ReconciliationBatch(
        tenant_id="tenant-demo",
        batch_id=f"b-{currency}",
        provider_id="prov-alfa",
        merchant_account="merchant-01",
        currency=currency,
        window_start=START,
        window_end=START + timedelta(days=1),
        business_timezone="America/La_Paz",
        source_pair=(SourceKind.INTERNAL_LEDGER, SourceKind.PROVIDER_REPORT),
        cutoff_at=START + timedelta(days=1, hours=6),
    )


def _run(batch: ReconciliationBatch, *items: SnapshotItem) -> list[Outcome]:
    return reconcile(RunInput(batch, items, (), COMPLETE, AFTER_CUTOFF))


def test_rc06_cross_currency_is_never_matched() -> None:
    bob = replace(PROVIDER, money=Money(10000, "BOB"))
    items = (SnapshotItem(1, LEDGER), SnapshotItem(2, bob))
    [usd] = _run(_batch("USD"), *items)
    [bob_side] = _run(_batch("BOB"), *items)
    assert usd.match_status is MatchStatus.UNMATCHED
    assert usd.discrepancy_types == (DiscrepancyType.MISSING_EXTERNAL,)
    assert bob_side.discrepancy_types == (DiscrepancyType.MISSING_INTERNAL,)


def test_rc11_offsets_resolve_to_the_same_economic_window() -> None:
    late_la_paz = datetime(2026, 9, 1, 23, 30, tzinfo=timezone(timedelta(hours=-4)))
    ledger = replace(LEDGER, occurred_at=DualTime.from_aware(late_la_paz))
    provider = replace(PROVIDER, occurred_at=DualTime.from_aware(late_la_paz.astimezone(UTC)))
    assert ledger.occurred_at.utc == provider.occurred_at.utc
    assert (ledger.occurred_at.offset_minutes, provider.occurred_at.offset_minutes) == (-240, 0)
    [exact] = _run(_batch(), SnapshotItem(1, ledger), SnapshotItem(2, provider))
    assert exact.match_status is MatchStatus.EXACT
    next_day = replace(LEDGER, occurred_at=DualTime.from_aware(late_la_paz + timedelta(hours=1)))
    assert _run(_batch(), SnapshotItem(1, next_day)) == []


def test_rc12_partial_refund_and_net_settlement_are_not_forced() -> None:
    refund = replace(
        PROVIDER,
        source_record_id="alf-2",
        operation_type=OperationType.REFUND,
        money=Money(3000, "USD"),
    )
    outcomes = _run(
        _batch(), SnapshotItem(1, LEDGER), SnapshotItem(2, PROVIDER), SnapshotItem(3, refund)
    )
    by_op = {o.operation_type: o for o in outcomes}
    assert by_op[OperationType.CAPTURE].match_status is MatchStatus.EXACT
    assert by_op[OperationType.REFUND].match_status is MatchStatus.UNMATCHED
    assert by_op[OperationType.REFUND].left_ids == ()
    net = replace(PROVIDER, money=Money(9700, "USD"))
    [linked] = _run(_batch(), SnapshotItem(1, LEDGER), SnapshotItem(2, net))
    assert linked.match_status is MatchStatus.UNMATCHED
    assert linked.discrepancy_types == (DiscrepancyType.AMOUNT_MISMATCH,)
    assert linked.amount_difference_minor == -300


@pytest.mark.parametrize("seed", [1, 7, 20260929])
def test_benchmark_550_payments_match_oracle_with_no_false_exact(seed: int) -> None:
    files = generate(seed=seed, per_scenario=50, version="v2").files()
    got, want = run_files(files), expected(files)
    assert len(want) == 550
    assert {ref for ref, w in want.items() if got.get(ref) != w} == set()
    predicted_exact = {ref for ref, c in got.items() if c.match_status == "EXACT"}
    assert predicted_exact == {ref for ref, w in want.items() if w.match_status == "EXACT"}


MODEL_MODULES = {"httpx", "openai", "anthropic", "ollama", "requests", "urllib", "recon_agents"}


def test_rc01_deterministic_path_has_no_model_or_http_client() -> None:
    """Exact matches cost zero model calls: the engine cannot even import a client."""
    roots = [
        ROOT / "packages/domain/src/recon_domain",
        ROOT / "packages/store/src/recon_store",
        ROOT / "apps/worker/src/recon_worker",
    ]
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else []
                )
                for name in names:
                    assert name.split(".")[0] not in MODEL_MODULES, f"{path}: {name}"


def test_ingest_subject_carries_identity() -> None:
    subject = ingest_subject("tenant-demo", SourceKind.PROVIDER_REPORT, "prov-alfa")
    assert parse_ingest_subject(subject) == ("tenant-demo", SourceKind.PROVIDER_REPORT, "prov-alfa")
    for bad in (
        "recon.ingest.t.provider_report",
        "recon.ingest.t.bogus.p",
        "x.y.t.provider_report.p",
    ):
        with pytest.raises(PoisonMessageError):
            parse_ingest_subject(bad)


@pytest.mark.parametrize(
    "envelope",
    [
        {"event_id": "not-a-uuid", "record": {}},
        {"event_id": "4b0c3d43-6f53-4c3c-9b9e-2d1c0b8a0d11", "record": "csv"},
        {"event_id": "4b0c3d43-6f53-4c3c-9b9e-2d1c0b8a0d11", "record": {"amount": 10}},
        {"event_id": "4b0c3d43-6f53-4c3c-9b9e-2d1c0b8a0d11", "record": {"evil_column": "x"}},
    ],
)
def test_malformed_events_are_poison_before_touching_storage(envelope: dict[str, object]) -> None:
    subject = ingest_subject("tenant-demo", SourceKind.PROVIDER_REPORT, "prov-alfa")
    with pytest.raises(PoisonMessageError):
        handle_observation_event(None, envelope, subject)  # type: ignore[arg-type]


def test_malformed_run_event_is_poison() -> None:
    with pytest.raises(PoisonMessageError):
        handle_run_requested(None, {"event_id": "x"})  # type: ignore[arg-type]
