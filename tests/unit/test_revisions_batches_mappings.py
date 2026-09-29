"""M1 T03/T04/T05: revision policy, batch windows and versioned mappings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon_domain.batch import ReconciliationBatch
from recon_domain.mappings import UnknownMappingError, vocabulary
from recon_domain.money import Money
from recon_domain.observation import DomainError, DualTime, ObservationStatus, SourceKind
from recon_domain.revisions import IngestOutcome, StoredRevision, decide

from .domain_support import observation

H1, H2 = "a" * 64, "b" * 64


def test_revision_outcomes() -> None:
    assert decide([], 1, H1) is IngestOutcome.CREATED
    history = [StoredRevision(1, H1)]
    assert decide(history, 1, H1) is IngestOutcome.DUPLICATE
    assert decide(history, 1, H2) is IngestOutcome.CONFLICT
    assert decide(history, 2, H2) is IngestOutcome.NEW_REVISION
    assert decide([StoredRevision(3, H1)], 2, H2) is IngestOutcome.STALE_REVISION


@given(
    st.lists(st.tuples(st.integers(1, 20), st.sampled_from([H1, H2])), max_size=10),
    st.integers(1, 20),
    st.sampled_from([H1, H2]),
)
def test_replaying_a_stored_revision_never_creates_an_effect(
    history: list[tuple[int, str]], revision: int, raw_hash: str
) -> None:
    stored = {rev: h for rev, h in history}
    outcome = decide([StoredRevision(r, h) for r, h in stored.items()], revision, raw_hash)
    if revision in stored:
        assert not outcome.persists
        assert (outcome is IngestOutcome.DUPLICATE) == (stored[revision] == raw_hash)
    else:
        assert outcome.persists


def _batch(**overrides: object) -> ReconciliationBatch:
    start = datetime(2026, 9, 1, 4, 0, tzinfo=UTC)
    values: dict[str, object] = {
        "tenant_id": "tenant-demo",
        "batch_id": "batch-2026-09-01",
        "provider_id": "prov-alfa",
        "merchant_account": "merchant-01",
        "currency": "USD",
        "window_start": start,
        "window_end": start + timedelta(days=1),
        "business_timezone": "America/La_Paz",
        "source_pair": (SourceKind.INTERNAL_LEDGER, SourceKind.PROVIDER_REPORT),
        "cutoff_at": start + timedelta(days=1, hours=6),
    }
    values.update(overrides)
    return ReconciliationBatch(**values)  # type: ignore[arg-type]


def test_batch_window_is_half_open() -> None:
    batch = _batch()
    assert batch.contains(batch.window_start)
    assert not batch.contains(batch.window_end)
    assert batch.contains(batch.window_end - timedelta(microseconds=1))


def test_batch_admits_only_its_scope() -> None:
    batch = _batch()
    inside = observation(occurred_at=DualTime.parse("2026-09-01T08:00:00-04:00"))
    assert batch.admits(inside)
    assert not batch.admits(observation(money=Money(1, "BOB")))
    assert not batch.admits(observation(merchant_account="merchant-02"))
    assert not batch.admits(observation(occurred_at=DualTime.parse("2026-09-02T00:00:00-04:00")))


def test_batch_closure_uses_cutoff() -> None:
    batch = _batch()
    assert not batch.is_closed(batch.window_end)
    assert batch.is_closed(batch.cutoff_at)


@pytest.mark.parametrize(
    "overrides",
    [
        {"window_end": datetime(2026, 9, 1, 4, 0, tzinfo=UTC)},
        {"cutoff_at": datetime(2026, 9, 1, 5, 0, tzinfo=UTC)},
        {"business_timezone": "Mars/Olympus"},
        {"source_pair": (SourceKind.INTERNAL_LEDGER, SourceKind.INTERNAL_LEDGER)},
        {"window_start": datetime(2026, 9, 1)},
        {"currency": "EUR"},
    ],
)
def test_invalid_batches_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _batch(**overrides)


def test_mappings_translate_known_values_and_reject_unknown() -> None:
    alfa = vocabulary(SourceKind.PROVIDER_REPORT, "prov-alfa")
    beta = vocabulary(SourceKind.PROVIDER_REPORT, "prov-beta")
    assert alfa.status("settled") is ObservationStatus.SUCCEEDED
    assert beta.status("OK") is ObservationStatus.SUCCEEDED
    with pytest.raises(UnknownMappingError):
        alfa.status("UNMAPPED_STATE")
    with pytest.raises(UnknownMappingError):
        beta.operation("CAPTURE")
    with pytest.raises(UnknownMappingError):
        vocabulary(SourceKind.PROVIDER_REPORT, "prov-gamma")
    assert issubclass(UnknownMappingError, DomainError)
