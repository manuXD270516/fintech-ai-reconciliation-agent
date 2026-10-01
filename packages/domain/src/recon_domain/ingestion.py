"""Anti-corruption layer: raw synthetic CSV rows -> canonical observations or rejections.

Rows are validated one by one: a bad row is quarantined with a reason code and never
guessed; valid rows in the same artifact are still accepted.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from recon_domain.mappings import UnknownMappingError, vocabulary
from recon_domain.money import Money, MoneyError
from recon_domain.observation import (
    DomainError,
    DualTime,
    SourceKind,
    TransactionObservation,
    canonical_hash,
    require_ident,
)
from recon_domain.synthetic import COLUMNS

PARSER_VERSION = "csv-parser/v1"
MAX_ROWS = 10_000


class ArtifactError(ValueError):
    """The artifact as a whole is unreadable (header, size); nothing is ingested."""


class RejectionCode(StrEnum):
    MISSING_FIELD = "missing_field"
    INVALID_FIELD = "invalid_field"
    INVALID_PRECISION = "invalid_precision"
    UNKNOWN_MAPPING = "unknown_mapping"
    SCOPE_VIOLATION = "scope_violation"


@dataclass(frozen=True, slots=True)
class RowRejection:
    row_number: int
    code: RejectionCode
    message: str
    payment_ref: str | None
    merchant_account: str | None
    currency: str | None
    raw_hash: str


@dataclass(frozen=True, slots=True)
class ParsedArtifact:
    observations: tuple[tuple[int, TransactionObservation], ...]
    rejections: tuple[RowRejection, ...]
    row_count: int


@dataclass
class _RowContext:
    row_number: int
    raw: dict[str, str]
    raw_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.raw_hash = canonical_hash(self.raw)

    def reject(self, code: RejectionCode, message: str) -> RowRejection:
        def safe(name: str) -> str | None:
            value = self.raw.get(name, "").strip()
            try:
                return require_ident(name, value) if value else None
            except DomainError:
                return None

        currency = self.raw.get("currency", "").strip()
        return RowRejection(
            self.row_number,
            code,
            message,
            safe("payment_ref"),
            safe("merchant_account"),
            currency if currency.isalpha() and len(currency) == 3 else None,
            self.raw_hash,
        )


def _parse_row(
    ctx: _RowContext, source: SourceKind, provider_id: str, tenant_id: str, received_at: datetime
) -> TransactionObservation | RowRejection:
    raw = ctx.raw
    for name in (
        "tenant_id",
        "source_record_id",
        "revision",
        "provider_id",
        "merchant_account",
        "operation",
        "payment_ref",
        "amount",
        "currency",
        "status",
        "occurred_at",
    ):
        if not raw.get(name, "").strip():
            return ctx.reject(RejectionCode.MISSING_FIELD, f"{name} is required")
    if raw["tenant_id"] != tenant_id or raw["provider_id"] != provider_id:
        return ctx.reject(
            RejectionCode.SCOPE_VIOLATION, "row tenant/provider differs from the artifact scope"
        )
    try:
        vocab = vocabulary(source, provider_id)
        status = vocab.status(raw["status"])
        operation = vocab.operation(raw["operation"])
    except UnknownMappingError as exc:
        return ctx.reject(RejectionCode.UNKNOWN_MAPPING, str(exc))
    try:
        money = Money.from_decimal(raw["amount"], raw["currency"].strip())
    except MoneyError as exc:
        code = (
            RejectionCode.INVALID_PRECISION
            if "precision" in str(exc)
            else RejectionCode.INVALID_FIELD
        )
        return ctx.reject(code, str(exc))
    try:
        revision = int(raw["revision"])
        received = (
            DualTime.parse(raw["received_at"])
            if raw.get("received_at", "").strip()
            else DualTime.from_aware(received_at)
        )
        return TransactionObservation(
            tenant_id=tenant_id,
            source=source,
            source_record_id=raw["source_record_id"].strip(),
            revision=revision,
            provider_id=provider_id,
            merchant_account=raw["merchant_account"].strip(),
            operation_type=operation,
            payment_ref=raw["payment_ref"].strip(),
            attempt_ref=raw.get("attempt_ref", "").strip() or None,
            money=money,
            status=status,
            occurred_at=DualTime.parse(raw["occurred_at"]),
            received_at=received,
            effective_at=None,
            raw_hash=ctx.raw_hash,
        )
    except (ValueError, DomainError) as exc:
        return ctx.reject(RejectionCode.INVALID_FIELD, str(exc).splitlines()[0][:200])


def rows_to_csv(rows: Iterable[Mapping[str, str]]) -> str:
    """Render raw rows with the canonical header (used for API/event payloads and fixtures).

    Unknown columns raise ArtifactError instead of being silently dropped.
    """
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        unknown = set(row) - set(COLUMNS)
        if unknown:
            raise ArtifactError(f"unknown columns: {sorted(unknown)}")
        writer.writerow(row)
    return out.getvalue()


def parse_csv(
    text: str,
    *,
    source: SourceKind,
    provider_id: str,
    tenant_id: str,
    received_at: datetime,
) -> ParsedArtifact:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != COLUMNS:
        raise ArtifactError(f"CSV header must be exactly: {','.join(COLUMNS)}")
    observations: list[tuple[int, TransactionObservation]] = []
    rejections: list[RowRejection] = []
    count = 0
    for count, raw in enumerate(reader, start=1):
        if count > MAX_ROWS:
            raise ArtifactError(f"artifact exceeds {MAX_ROWS} rows")
        if None in raw or any(v is None for v in raw.values()):
            ctx = _RowContext(count, {k: v or "" for k, v in raw.items() if k is not None})
            rejections.append(ctx.reject(RejectionCode.INVALID_FIELD, "wrong number of columns"))
            continue
        ctx = _RowContext(count, dict(raw))
        result = _parse_row(ctx, source, provider_id, tenant_id, received_at)
        if isinstance(result, RowRejection):
            rejections.append(result)
        else:
            observations.append((count, result))
    return ParsedArtifact(tuple(observations), tuple(rejections), count)
