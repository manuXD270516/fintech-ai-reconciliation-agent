"""Reconciliation batches: half-open windows with business timezone, source pair and cutoff."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from recon_domain.money import exponent_of
from recon_domain.observation import DomainError, SourceKind, TransactionObservation, require_ident


def _require_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(None):
        raise DomainError(f"{name} must be timezone-aware UTC")


@dataclass(frozen=True, slots=True)
class ReconciliationBatch:
    tenant_id: str
    batch_id: str
    provider_id: str
    merchant_account: str
    currency: str
    window_start: datetime
    window_end: datetime
    business_timezone: str
    source_pair: tuple[SourceKind, SourceKind]
    cutoff_at: datetime

    def __post_init__(self) -> None:
        for name in ("tenant_id", "batch_id", "provider_id", "merchant_account"):
            require_ident(name, getattr(self, name))
        exponent_of(self.currency)
        for name in ("window_start", "window_end", "cutoff_at"):
            _require_utc(name, getattr(self, name))
        if self.window_end <= self.window_start:
            raise DomainError("window_end must be after window_start")
        if self.cutoff_at < self.window_end:
            raise DomainError("cutoff_at cannot be before window_end")
        try:
            ZoneInfo(self.business_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise DomainError("business_timezone must be a valid IANA zone") from None
        left, right = self.source_pair
        if left == right:
            raise DomainError("source_pair needs two different sources")

    def contains(self, instant: datetime) -> bool:
        """Half-open window [start, end)."""
        return self.window_start <= instant < self.window_end

    def admits(self, observation: TransactionObservation) -> bool:
        return (
            observation.tenant_id == self.tenant_id
            and observation.provider_id == self.provider_id
            and observation.merchant_account == self.merchant_account
            and observation.money.currency == self.currency
            and observation.source in self.source_pair
            and self.contains(observation.occurred_at.utc)
        )

    def is_closed(self, now: datetime) -> bool:
        _require_utc("now", now)
        return now >= self.cutoff_at
