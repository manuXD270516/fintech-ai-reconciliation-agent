"""Outbox relay helpers. Publication is at-least-once; consumers dedupe with the inbox."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, select, update

from recon_store.tables import outbox


@dataclass(frozen=True, slots=True)
class PendingEvent:
    event_id: uuid.UUID
    event_type: str
    envelope: dict[str, Any]


def pending(engine: Engine, limit: int = 100) -> list[PendingEvent]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(outbox)
            .where(outbox.c.published_at.is_(None))
            .order_by(outbox.c.occurred_at, outbox.c.event_id)
            .limit(limit)
        ).mappings()
        return [
            PendingEvent(
                r["event_id"],
                r["event_type"],
                {
                    "event_id": str(r["event_id"]),
                    "event_type": r["event_type"],
                    "schema_version": r["schema_version"],
                    "tenant_id": r["tenant_id"],
                    "aggregate_id": r["aggregate_id"],
                    "aggregate_version": r["aggregate_version"],
                    "occurred_at": r["occurred_at"].isoformat(),
                    "correlation_id": r["correlation_id"],
                    "causation_id": r["causation_id"],
                    "payload": r["payload"],
                },
            )
            for r in rows
        ]


def mark_published(engine: Engine, event_ids: list[uuid.UUID], at: datetime) -> None:
    if not event_ids:
        return
    with engine.begin() as conn:
        conn.execute(
            update(outbox)
            .where(outbox.c.event_id.in_(event_ids), outbox.c.published_at.is_(None))
            .values(published_at=at)
        )


def mark_failed(engine: Engine, event_id: uuid.UUID, error: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(outbox)
            .where(outbox.c.event_id == event_id)
            .values(attempts=outbox.c.attempts + 1, last_error=error[:300])
        )
