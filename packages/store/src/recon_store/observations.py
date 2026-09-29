"""Atomic, idempotent observation ingestion: state + audit + outbox in one transaction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, RowMapping, func, insert, select

from recon_domain.money import Money, exponent_of
from recon_domain.observation import (
    DualTime,
    ObservationKey,
    ObservationStatus,
    OperationType,
    SourceKind,
    TransactionObservation,
)
from recon_domain.revisions import IngestOutcome, StoredRevision, decide
from recon_store.tables import audit_entries, observations, outbox

OBSERVATION_RECORDED = "ObservationRecorded"


@dataclass(frozen=True, slots=True)
class IngestResult:
    outcome: IngestOutcome
    observation_id: int | None
    current_revision: int | None


def _dual(prefix: str, value: DualTime | None) -> dict[str, Any]:
    return {
        f"{prefix}_at": value.utc if value else None,
        f"{prefix}_offset_minutes": value.offset_minutes if value else None,
    }


def to_row(obs: TransactionObservation) -> dict[str, Any]:
    return {
        "tenant_id": obs.tenant_id,
        "source": obs.source.value,
        "source_record_id": obs.source_record_id,
        "revision": obs.revision,
        "provider_id": obs.provider_id,
        "merchant_account": obs.merchant_account,
        "operation_type": obs.operation_type.value,
        "payment_ref": obs.payment_ref,
        "attempt_ref": obs.attempt_ref,
        "amount_minor": obs.money.amount_minor,
        "currency": obs.money.currency,
        "currency_exponent": exponent_of(obs.money.currency),
        "status": obs.status.value,
        **_dual("occurred", obs.occurred_at),
        **_dual("received", obs.received_at),
        **_dual("effective", obs.effective_at),
        "raw_hash": obs.raw_hash,
        "normalization_version": obs.normalization_version,
    }


def _time(at: datetime | None, offset: int | None) -> DualTime | None:
    return None if at is None or offset is None else DualTime(at, offset)


def from_row(row: RowMapping) -> TransactionObservation:
    occurred = _time(row["occurred_at"], row["occurred_offset_minutes"])
    received = _time(row["received_at"], row["received_offset_minutes"])
    if occurred is None or received is None:
        raise ValueError("stored observation without mandatory timestamps")
    return TransactionObservation(
        tenant_id=row["tenant_id"],
        source=SourceKind(row["source"]),
        source_record_id=row["source_record_id"],
        revision=row["revision"],
        provider_id=row["provider_id"],
        merchant_account=row["merchant_account"],
        operation_type=OperationType(row["operation_type"]),
        payment_ref=row["payment_ref"],
        attempt_ref=row["attempt_ref"],
        money=Money(row["amount_minor"], row["currency"]),
        status=ObservationStatus(row["status"]),
        occurred_at=occurred,
        received_at=received,
        effective_at=_time(row["effective_at"], row["effective_offset_minutes"]),
        raw_hash=row["raw_hash"],
        normalization_version=row["normalization_version"],
    )


def _lock_key(conn: Connection, key: ObservationKey) -> None:
    """Serialize concurrent writers of the same observation key inside this transaction."""
    token = f"{key.tenant_id}|{key.source.value}|{key.source_record_id}"
    conn.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(token, 0))))


class ObservationStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def ingest(
        self, obs: TransactionObservation, *, actor: str, correlation_id: str
    ) -> IngestResult:
        with self.engine.begin() as conn:
            return self.ingest_in(conn, obs, actor=actor, correlation_id=correlation_id)

    def ingest_in(
        self,
        conn: Connection,
        obs: TransactionObservation,
        *,
        actor: str,
        correlation_id: str,
        causation_id: str | None = None,
    ) -> IngestResult:
        key = obs.key
        _lock_key(conn, key)
        rows = conn.execute(
            select(observations.c.id, observations.c.revision, observations.c.raw_hash).where(
                observations.c.tenant_id == key.tenant_id,
                observations.c.source == key.source.value,
                observations.c.source_record_id == key.source_record_id,
            )
        ).all()
        outcome = decide(
            (StoredRevision(r.revision, r.raw_hash) for r in rows), obs.revision, obs.raw_hash
        )
        resource_id = f"{key.source.value}/{key.source_record_id}"

        if outcome is IngestOutcome.DUPLICATE:
            existing = next(r.id for r in rows if r.revision == obs.revision)
            return IngestResult(outcome, existing, max(r.revision for r in rows))

        if outcome is IngestOutcome.CONFLICT:
            conn.execute(
                insert(audit_entries).values(
                    tenant_id=key.tenant_id,
                    actor=actor,
                    action="observation.ingest",
                    resource_type="observation",
                    resource_id=resource_id,
                    resource_version=obs.revision,
                    outcome="conflict",
                    correlation_id=correlation_id,
                    details={"raw_hash": obs.raw_hash, "reason": "same revision, different hash"},
                )
            )
            return IngestResult(outcome, None, max(r.revision for r in rows))

        new_id: int = conn.execute(
            insert(observations).values(**to_row(obs)).returning(observations.c.id)
        ).scalar_one()
        current = max([obs.revision, *(r.revision for r in rows)])
        conn.execute(
            insert(audit_entries).values(
                tenant_id=key.tenant_id,
                actor=actor,
                action="observation.ingest",
                resource_type="observation",
                resource_id=resource_id,
                resource_version=obs.revision,
                outcome=outcome.value,
                correlation_id=correlation_id,
                details={"observation_id": new_id, "raw_hash": obs.raw_hash},
            )
        )
        conn.execute(
            insert(outbox).values(
                event_id=uuid.uuid4(),
                event_type=OBSERVATION_RECORDED,
                schema_version=1,
                tenant_id=key.tenant_id,
                aggregate_id=resource_id,
                aggregate_version=obs.revision,
                correlation_id=correlation_id,
                causation_id=causation_id,
                payload={
                    "observation_id": new_id,
                    "outcome": outcome.value,
                    "current_revision": current,
                },
            )
        )
        return IngestResult(outcome, new_id, current)

    def history(self, key: ObservationKey) -> list[TransactionObservation]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(observations)
                .where(
                    observations.c.tenant_id == key.tenant_id,
                    observations.c.source == key.source.value,
                    observations.c.source_record_id == key.source_record_id,
                )
                .order_by(observations.c.revision)
            ).mappings()
            return [from_row(r) for r in rows]
