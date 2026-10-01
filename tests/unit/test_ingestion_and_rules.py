"""M2 T01/T02: CSV anti-corruption layer and deterministic rule edge cases."""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from recon_domain.batch import ReconciliationBatch
from recon_domain.ingestion import ArtifactError, RejectionCode, parse_csv
from recon_domain.money import Money
from recon_domain.observation import DualTime, ObservationStatus, SourceKind
from recon_domain.oracle import to_csv
from recon_domain.reconciliation import (
    DiscrepancyType,
    MatchStatus,
    RejectedRef,
    RunInput,
    SnapshotItem,
    reconcile,
)
from recon_domain.synthetic import COLUMNS

from .domain_support import observation

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
ROW = {
    "tenant_id": "tenant-demo",
    "source_record_id": "alf-1",
    "revision": "1",
    "provider_id": "prov-alfa",
    "merchant_account": "merchant-01",
    "operation": "CAPTURE",
    "payment_ref": "pay-1",
    "attempt_ref": "",
    "amount": "10.00",
    "currency": "USD",
    "status": "SETTLED",
    "occurred_at": "2026-09-01T08:00:00-04:00",
    "received_at": "",
}


def _parse(*rows: dict[str, str], tenant: str = "tenant-demo") -> object:
    return parse_csv(
        to_csv(rows),
        source=SourceKind.PROVIDER_REPORT,
        provider_id="prov-alfa",
        tenant_id=tenant,
        received_at=NOW,
    )


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"amount": "10.005"}, RejectionCode.INVALID_PRECISION),
        ({"amount": "ten"}, RejectionCode.INVALID_FIELD),
        ({"status": "UNMAPPED_STATE"}, RejectionCode.UNKNOWN_MAPPING),
        ({"operation": "CAP"}, RejectionCode.UNKNOWN_MAPPING),
        ({"tenant_id": "tenant-other"}, RejectionCode.SCOPE_VIOLATION),
        ({"provider_id": "prov-beta"}, RejectionCode.SCOPE_VIOLATION),
        ({"payment_ref": ""}, RejectionCode.MISSING_FIELD),
        ({"occurred_at": "2026-09-01T08:00:00"}, RejectionCode.INVALID_FIELD),
        ({"revision": "0"}, RejectionCode.INVALID_FIELD),
        ({"currency": "EUR"}, RejectionCode.INVALID_FIELD),
    ],
)
def test_bad_rows_are_quarantined_without_blocking_good_rows(
    change: dict[str, str], code: RejectionCode
) -> None:
    parsed = _parse(dict(ROW, **change, source_record_id="alf-bad"), ROW)
    assert [o.source_record_id for _, o in parsed.observations] == ["alf-1"]  # type: ignore[attr-defined]
    [rejection] = parsed.rejections  # type: ignore[attr-defined]
    assert rejection.code is code and rejection.row_number == 1


def test_valid_row_maps_vocabulary_and_keeps_raw_hash() -> None:
    parsed = _parse(ROW)
    [(_, obs)] = parsed.observations  # type: ignore[attr-defined]
    assert obs.status is ObservationStatus.SUCCEEDED
    assert obs.money == Money(1000, "USD")
    assert obs.received_at.utc == NOW
    assert _parse(ROW).observations[0][1].raw_hash == obs.raw_hash  # type: ignore[attr-defined]


def test_wrong_header_rejects_whole_artifact() -> None:
    with pytest.raises(ArtifactError):
        parse_csv(
            "a,b\n1,2\n",
            source=SourceKind.PROVIDER_REPORT,
            provider_id="prov-alfa",
            tenant_id="tenant-demo",
            received_at=NOW,
        )
    assert tuple(to_csv([]).strip().split(",")) == COLUMNS


START = datetime(2026, 9, 1, 4, 0, tzinfo=UTC)
BATCH = ReconciliationBatch(
    tenant_id="tenant-demo",
    batch_id="b-1",
    provider_id="prov-alfa",
    merchant_account="merchant-01",
    currency="USD",
    window_start=START,
    window_end=START + timedelta(days=1),
    business_timezone="America/La_Paz",
    source_pair=(SourceKind.INTERNAL_LEDGER, SourceKind.PROVIDER_REPORT),
    cutoff_at=START + timedelta(days=1, hours=6),
)
LEDGER = observation()
PROVIDER = observation(
    source=SourceKind.PROVIDER_REPORT, source_record_id="alf-000001", attempt_ref=None
)


def _run(
    *items: SnapshotItem,
    now: datetime = NOW + timedelta(days=1),
    complete: bool = True,
    rejections: tuple[RejectedRef, ...] = (),
) -> list[object]:
    flags = {SourceKind.INTERNAL_LEDGER: complete, SourceKind.PROVIDER_REPORT: complete}
    return reconcile(RunInput(BATCH, items, rejections, flags, now))  # type: ignore[return-value]


def test_exact_requires_identical_money_and_status_zero_tolerance() -> None:
    [exact] = _run(SnapshotItem(1, LEDGER), SnapshotItem(2, PROVIDER))
    assert exact.match_status is MatchStatus.EXACT  # type: ignore[attr-defined]
    off_by_one = replace(PROVIDER, money=Money(9999, "USD"))
    [linked] = _run(SnapshotItem(1, LEDGER), SnapshotItem(2, off_by_one))
    assert linked.match_status is MatchStatus.UNMATCHED  # type: ignore[attr-defined]
    assert linked.discrepancy_types == (DiscrepancyType.AMOUNT_MISMATCH,)  # type: ignore[attr-defined]
    assert linked.amount_difference_minor == -1  # type: ignore[attr-defined]


def test_amount_and_time_alone_never_match() -> None:
    other_ref = replace(PROVIDER, payment_ref="ext-9", attempt_ref=None)
    outcomes = _run(SnapshotItem(1, LEDGER), SnapshotItem(2, other_ref))
    assert {o.match_status for o in outcomes} == {MatchStatus.UNMATCHED}  # type: ignore[attr-defined]


def test_equal_weak_candidates_keep_ambiguity() -> None:
    a = replace(PROVIDER, payment_ref="ext-1", attempt_ref="pay-0001-a1")
    b = replace(a, payment_ref="ext-2", source_record_id="alf-000002")
    outcomes = _run(SnapshotItem(1, LEDGER), SnapshotItem(2, a), SnapshotItem(3, b))
    ledger_outcome = next(o for o in outcomes if o.left_ids == (1,))  # type: ignore[attr-defined]
    assert ledger_outcome.rule == "weak_ambiguous"  # type: ignore[attr-defined]
    assert ledger_outcome.alternatives == (2, 3)  # type: ignore[attr-defined]
    assert all(o.match_status is not MatchStatus.PROBABLE for o in outcomes)  # type: ignore[attr-defined]


def test_missing_waits_until_cutoff_and_completeness() -> None:
    [early] = _run(SnapshotItem(1, LEDGER), now=START + timedelta(hours=10))
    [incomplete] = _run(SnapshotItem(1, LEDGER), complete=False)
    [closed] = _run(SnapshotItem(1, LEDGER))
    assert early.discrepancy_types == (DiscrepancyType.WAITING_SOURCE,)  # type: ignore[attr-defined]
    assert incomplete.discrepancy_types == (DiscrepancyType.WAITING_SOURCE,)  # type: ignore[attr-defined]
    assert closed.discrepancy_types == (DiscrepancyType.MISSING_EXTERNAL,)  # type: ignore[attr-defined]


def test_scope_isolation_and_processing_errors() -> None:
    foreign = replace(PROVIDER, merchant_account="merchant-02")
    outcomes = _run(SnapshotItem(1, LEDGER), SnapshotItem(2, foreign))
    assert [o.left_ids for o in outcomes] == [(1,)]  # type: ignore[attr-defined]
    rejected = (RejectedRef(SourceKind.PROVIDER_REPORT, "pay-0001", "merchant-01", "USD"),)
    [err] = _run(SnapshotItem(1, LEDGER), rejections=rejected)
    assert err.match_status is MatchStatus.NOT_EVALUATED  # type: ignore[attr-defined]
    assert err.discrepancy_types == (DiscrepancyType.PROCESSING_ERROR,)  # type: ignore[attr-defined]


def test_result_is_independent_of_input_order() -> None:
    items = [
        SnapshotItem(
            i,
            replace(
                LEDGER,
                source_record_id=f"led-{i}",
                payment_ref=f"pay-{i}",
                occurred_at=DualTime(START + timedelta(minutes=i), -240),
            ),
        )
        for i in range(1, 30)
    ]
    items += [
        SnapshotItem(
            100 + i, replace(PROVIDER, source_record_id=f"alf-{i}", payment_ref=f"pay-{i}")
        )
        for i in range(1, 30, 2)
    ]
    baseline = _run(*items)
    shuffled = items[:]
    random.Random(7).shuffle(shuffled)
    assert _run(*shuffled) == baseline
