"""Immutable transaction observations, scoped references and dual timestamps."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from recon_domain.money import Money

NORMALIZATION_VERSION = "normalization/v1"

_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DomainError(ValueError):
    """A value violates a domain invariant."""


class SourceKind(StrEnum):
    INTERNAL_LEDGER = "internal_ledger"
    PROVIDER_REPORT = "provider_report"


class OperationType(StrEnum):
    AUTHORIZATION = "authorization"
    CAPTURE = "capture"
    REFUND = "refund"
    CHARGEBACK = "chargeback"


class ObservationStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REVERSED = "reversed"


def require_ident(name: str, value: str) -> str:
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise DomainError(f"{name} must match {_IDENT.pattern}")
    return value


@dataclass(frozen=True, slots=True)
class DualTime:
    """An instant kept both in UTC and with the offset the source reported."""

    utc: datetime
    offset_minutes: int

    def __post_init__(self) -> None:
        if self.utc.tzinfo is None or self.utc.utcoffset() != UTC.utcoffset(None):
            raise DomainError("DualTime.utc must be timezone-aware UTC")
        if not -1080 <= self.offset_minutes <= 1080:
            raise DomainError("offset_minutes must be within +/-18h")

    @classmethod
    def from_aware(cls, value: datetime) -> DualTime:
        offset = value.utcoffset()
        if value.tzinfo is None or offset is None:
            raise DomainError("naive timestamps are rejected; an explicit offset is required")
        return cls(value.astimezone(UTC), int(offset.total_seconds() // 60))

    @classmethod
    def parse(cls, text: str) -> DualTime:
        try:
            return cls.from_aware(datetime.fromisoformat(text))
        except ValueError as exc:
            raise DomainError(f"invalid RFC 3339 timestamp: {exc}") from None


@dataclass(frozen=True, slots=True)
class ScopedRef:
    """External identifiers are only meaningful inside a provider and merchant account."""

    provider_id: str
    merchant_account: str
    value: str

    def __post_init__(self) -> None:
        require_ident("provider_id", self.provider_id)
        require_ident("merchant_account", self.merchant_account)
        require_ident("reference", self.value)


@dataclass(frozen=True, slots=True)
class ObservationKey:
    tenant_id: str
    source: SourceKind
    source_record_id: str


def canonical_hash(raw: Mapping[str, object]) -> str:
    """SHA-256 over a canonical JSON rendering of the original record."""
    blob = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TransactionObservation:
    tenant_id: str
    source: SourceKind
    source_record_id: str
    revision: int
    provider_id: str
    merchant_account: str
    operation_type: OperationType
    payment_ref: str
    attempt_ref: str | None
    money: Money
    status: ObservationStatus
    occurred_at: DualTime
    received_at: DualTime
    effective_at: DualTime | None
    raw_hash: str
    normalization_version: str = NORMALIZATION_VERSION

    def __post_init__(self) -> None:
        require_ident("tenant_id", self.tenant_id)
        require_ident("source_record_id", self.source_record_id)
        if type(self.revision) is not int or self.revision < 1:
            raise DomainError("revision must be an int >= 1")
        ScopedRef(self.provider_id, self.merchant_account, self.payment_ref)
        if self.attempt_ref is not None:
            require_ident("attempt_ref", self.attempt_ref)
        if not _SHA256.fullmatch(self.raw_hash):
            raise DomainError("raw_hash must be a lowercase SHA-256 hex digest")
        for name in ("source", "operation_type", "status"):
            enum_type = {
                "source": SourceKind,
                "operation_type": OperationType,
                "status": ObservationStatus,
            }[name]
            if not isinstance(getattr(self, name), enum_type):
                raise DomainError(f"{name} must be a {enum_type.__name__}")

    @property
    def key(self) -> ObservationKey:
        return ObservationKey(self.tenant_id, self.source, self.source_record_id)

    @property
    def reference(self) -> ScopedRef:
        return ScopedRef(self.provider_id, self.merchant_account, self.payment_ref)

    @property
    def comparison_scope(self) -> tuple[str, str, str, str, OperationType]:
        """Observations are only ever compared inside the same scope (invariant 1)."""
        return (
            self.tenant_id,
            self.provider_id,
            self.merchant_account,
            self.money.currency,
            self.operation_type,
        )


def comparable(a: TransactionObservation, b: TransactionObservation) -> bool:
    return a.comparison_scope == b.comparison_scope and a.source != b.source
