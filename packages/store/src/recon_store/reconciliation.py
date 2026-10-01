"""Batches, run requests and run execution. A rerun always creates a new run version."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, Engine, RowMapping, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from recon_domain.batch import ReconciliationBatch
from recon_domain.observation import SourceKind
from recon_domain.reconciliation import (
    RULESET_VERSION,
    MatchStatus,
    RejectedRef,
    RunInput,
    SnapshotItem,
    reconcile,
    snapshot_hash,
)
from recon_store.observations import from_row
from recon_store.tables import (
    audit_entries,
    batches,
    inbox,
    observations,
    outbox,
    rejections,
    results,
    runs,
)

RECONCILIATION_REQUESTED = "ReconciliationRequested"
RECONCILIATION_COMPLETED = "ReconciliationCompleted"


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


def _batch_from_row(row: RowMapping) -> ReconciliationBatch:
    return ReconciliationBatch(
        tenant_id=row["tenant_id"],
        batch_id=row["batch_id"],
        provider_id=row["provider_id"],
        merchant_account=row["merchant_account"],
        currency=row["currency"],
        window_start=row["window_start"],
        window_end=row["window_end"],
        business_timezone=row["business_timezone"],
        source_pair=(SourceKind(row["left_source"]), SourceKind(row["right_source"])),
        cutoff_at=row["cutoff_at"],
    )


@dataclass(frozen=True, slots=True)
class BatchView:
    batch: ReconciliationBatch
    left_complete: bool
    right_complete: bool
    version: int


def _batch_view(row: RowMapping) -> BatchView:
    return BatchView(
        _batch_from_row(row), row["left_complete"], row["right_complete"], row["version"]
    )


def _audit(conn: Connection, **values: Any) -> None:
    conn.execute(insert(audit_entries).values(**values))


def _event(
    conn: Connection,
    event_type: str,
    tenant_id: str,
    aggregate_id: str,
    version: int,
    correlation_id: str,
    payload: dict[str, Any],
    causation_id: str | None = None,
) -> None:
    conn.execute(
        insert(outbox).values(
            event_id=uuid.uuid4(),
            event_type=event_type,
            schema_version=1,
            tenant_id=tenant_id,
            aggregate_id=aggregate_id,
            aggregate_version=version,
            correlation_id=correlation_id,
            causation_id=causation_id,
            payload=payload,
        )
    )


class ReconciliationService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # --- batches ------------------------------------------------------------------

    def create_batch(self, batch: ReconciliationBatch, *, actor: str, correlation_id: str) -> None:
        left, right = batch.source_pair
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    insert(batches).values(
                        tenant_id=batch.tenant_id,
                        batch_id=batch.batch_id,
                        provider_id=batch.provider_id,
                        merchant_account=batch.merchant_account,
                        currency=batch.currency,
                        window_start=batch.window_start,
                        window_end=batch.window_end,
                        business_timezone=batch.business_timezone,
                        left_source=left.value,
                        right_source=right.value,
                        cutoff_at=batch.cutoff_at,
                    )
                )
                _audit(
                    conn,
                    tenant_id=batch.tenant_id,
                    actor=actor,
                    action="batch.create",
                    resource_type="batch",
                    resource_id=batch.batch_id,
                    resource_version=1,
                    outcome="created",
                    correlation_id=correlation_id,
                )
        except IntegrityError as exc:
            raise ConflictError(batch.batch_id) from exc

    def get_batch(self, tenant_id: str, batch_id: str, conn: Connection | None = None) -> BatchView:
        stmt = select(batches).where(
            batches.c.tenant_id == tenant_id, batches.c.batch_id == batch_id
        )
        if conn is not None:
            row = conn.execute(stmt).mappings().first()
        else:
            with self.engine.connect() as c:
                row = c.execute(stmt).mappings().first()
        if row is None:
            raise NotFoundError(batch_id)
        return _batch_view(row)

    def mark_complete(
        self, tenant_id: str, batch_id: str, source: SourceKind, *, actor: str, correlation_id: str
    ) -> BatchView:
        with self.engine.begin() as conn:
            view = self.get_batch(tenant_id, batch_id, conn)
            left, right = view.batch.source_pair
            if source not in (left, right):
                raise ConflictError(f"{source} is not part of the batch source pair")
            column = "left_complete" if source == left else "right_complete"
            conn.execute(
                update(batches)
                .where(batches.c.tenant_id == tenant_id, batches.c.batch_id == batch_id)
                .values({column: True, "version": batches.c.version + 1})
            )
            _audit(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="batch.source_complete",
                resource_type="batch",
                resource_id=batch_id,
                resource_version=view.version + 1,
                outcome="updated",
                correlation_id=correlation_id,
                details={"source": source.value},
            )
            return self.get_batch(tenant_id, batch_id, conn)

    # --- runs ---------------------------------------------------------------------

    def request_run(
        self, tenant_id: str, batch_id: str, *, actor: str, correlation_id: str
    ) -> tuple[uuid.UUID, int]:
        with self.engine.begin() as conn:
            self.get_batch(tenant_id, batch_id, conn)
            token = f"run|{tenant_id}|{batch_id}"
            conn.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(token, 0))))
            number = (
                int(
                    conn.execute(
                        select(func.coalesce(func.max(runs.c.run_number), 0)).where(
                            runs.c.tenant_id == tenant_id, runs.c.batch_id == batch_id
                        )
                    ).scalar_one()
                )
                + 1
            )
            run_id = uuid.uuid4()
            conn.execute(
                insert(runs).values(
                    id=run_id,
                    tenant_id=tenant_id,
                    batch_id=batch_id,
                    run_number=number,
                    status="requested",
                    ruleset_version=RULESET_VERSION,
                    requested_by=actor,
                    correlation_id=correlation_id,
                )
            )
            _audit(
                conn,
                tenant_id=tenant_id,
                actor=actor,
                action="run.request",
                resource_type="run",
                resource_id=str(run_id),
                resource_version=number,
                outcome="requested",
                correlation_id=correlation_id,
            )
            _event(
                conn,
                RECONCILIATION_REQUESTED,
                tenant_id,
                f"run/{run_id}",
                number,
                correlation_id,
                {"run_id": str(run_id), "batch_id": batch_id},
            )
            return run_id, number

    def execute_run(
        self, conn: Connection, run_id: uuid.UUID, now: datetime, causation_id: str | None = None
    ) -> dict[str, int]:
        run = (
            conn.execute(select(runs).where(runs.c.id == run_id).with_for_update())
            .mappings()
            .first()
        )
        if run is None:
            raise NotFoundError(str(run_id))
        if run["status"] != "requested":
            return {}
        view = self.get_batch(run["tenant_id"], run["batch_id"], conn)
        batch = view.batch
        latest = (
            select(observations)
            .where(
                observations.c.tenant_id == batch.tenant_id,
                observations.c.provider_id == batch.provider_id,
                observations.c.merchant_account == batch.merchant_account,
                observations.c.currency == batch.currency,
                observations.c.source.in_([s.value for s in batch.source_pair]),
            )
            .order_by(
                observations.c.source,
                observations.c.source_record_id,
                observations.c.revision.desc(),
            )
            .distinct(observations.c.source, observations.c.source_record_id)
        )
        snapshot = tuple(
            SnapshotItem(row["id"], from_row(row)) for row in conn.execute(latest).mappings()
        )
        rejected = tuple(
            RejectedRef(SourceKind(r.source), r.payment_ref, r.merchant_account, r.currency)
            for r in conn.execute(
                select(
                    rejections.c.source,
                    rejections.c.payment_ref,
                    rejections.c.merchant_account,
                    rejections.c.currency,
                ).where(
                    rejections.c.tenant_id == batch.tenant_id,
                    rejections.c.provider_id == batch.provider_id,
                    rejections.c.merchant_account == batch.merchant_account,
                    rejections.c.currency == batch.currency,
                    rejections.c.payment_ref.is_not(None),
                )
            )
        )
        left, right = batch.source_pair
        outcomes = reconcile(
            RunInput(
                batch,
                snapshot,
                rejected,
                {left: view.left_complete, right: view.right_complete},
                now,
            )
        )
        if outcomes:
            conn.execute(
                insert(results),
                [
                    {
                        "run_id": run_id,
                        "ordinal": i,
                        "payment_ref": o.payment_ref,
                        "operation_type": o.operation_type.value,
                        "match_status": o.match_status.value,
                        "rule": o.rule,
                        "discrepancy_types": [t.value for t in o.discrepancy_types],
                        "left_ids": list(o.left_ids),
                        "right_ids": list(o.right_ids),
                        "amount_difference_minor": o.amount_difference_minor,
                        "score": None if o.score is None else Decimal(str(o.score)),
                        "alternatives": list(o.alternatives),
                        "explanation": o.explanation,
                    }
                    for i, o in enumerate(outcomes, start=1)
                ],
            )
        summary = {s.value: sum(o.match_status is s for o in outcomes) for s in MatchStatus}
        summary["discrepancies"] = sum(bool(o.discrepancy_types) for o in outcomes)
        conn.execute(
            update(runs)
            .where(runs.c.id == run_id)
            .values(
                status="completed",
                snapshot_hash=snapshot_hash(snapshot),
                observation_count=len(snapshot),
                completed_at=now,
            )
        )
        _audit(
            conn,
            tenant_id=batch.tenant_id,
            actor="svc-reconciliation-worker",
            action="run.execute",
            resource_type="run",
            resource_id=str(run_id),
            resource_version=run["run_number"],
            outcome="completed",
            correlation_id=run["correlation_id"],
            details=summary,
        )
        _event(
            conn,
            RECONCILIATION_COMPLETED,
            batch.tenant_id,
            f"run/{run_id}",
            run["run_number"],
            run["correlation_id"],
            {"run_id": str(run_id), **summary},
            causation_id,
        )
        return summary

    def fail_run(self, run_id: uuid.UUID, error: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(runs)
                .where(runs.c.id == run_id, runs.c.status == "requested")
                .values(status="failed", error=error[:300])
            )

    def get_run(self, tenant_id: str, run_id: uuid.UUID) -> RowMapping:
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(runs).where(runs.c.id == run_id, runs.c.tenant_id == tenant_id))
                .mappings()
                .first()
            )
        if row is None:
            raise NotFoundError(str(run_id))
        return row

    def list_results(
        self,
        tenant_id: str,
        run_id: uuid.UUID,
        *,
        match_status: str | None = None,
        after: int = 0,
        limit: int = 100,
    ) -> list[RowMapping]:
        self.get_run(tenant_id, run_id)
        stmt = select(results).where(results.c.run_id == run_id, results.c.ordinal > after)
        if match_status:
            stmt = stmt.where(results.c.match_status == match_status)
        with self.engine.connect() as conn:
            return list(conn.execute(stmt.order_by(results.c.ordinal).limit(limit)).mappings())

    def status_counts(self, run_id: uuid.UUID) -> dict[str, int]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(results.c.match_status, func.count())
                .where(results.c.run_id == run_id)
                .group_by(results.c.match_status)
            ).all()
        return {r[0]: int(r[1]) for r in rows}


def record_inbox(conn: Connection, consumer: str, event_id: uuid.UUID) -> bool:
    """True if this (consumer, event) was not processed before; commits with the effect."""
    inserted = conn.execute(
        pg_insert(inbox)
        .values(consumer=consumer, event_id=event_id)
        .on_conflict_do_nothing(index_elements=["consumer", "event_id"])
        .returning(inbox.c.event_id)
    ).first()
    return inserted is not None
