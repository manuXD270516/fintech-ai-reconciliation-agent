"""Operational read model for metrics and alerts (M9).

Every figure is an aggregate across tenants: no tenant, subject, transaction or case IDs
leave this module, so the values can be exposed as low-cardinality metric labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import Connection, Engine, func, select, text
from sqlalchemy.dialects.postgresql import insert

from recon_store.tables import (
    audit_entries,
    cases,
    investigations,
    observations,
    outbox,
    recommendations,
    rejections,
    results,
    runs,
    service_heartbeats,
)

# Audited refusal of a human decision (segregation of duties, stale version, ...).
DECISION_DENIED = "decision.denied"
# Refusals and tool outcomes are counted over a sliding window so alerts can clear.
AUDIT_WINDOW = timedelta(hours=1)


def beat(engine: Engine, service: str, instance: str, now: datetime) -> None:
    """Upsert the liveness heartbeat of a background service."""
    stmt = insert(service_heartbeats).values(service=service, instance=instance, beat_at=now)
    with engine.begin() as conn:
        conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[service_heartbeats.c.service],
                set_={"instance": stmt.excluded.instance, "beat_at": stmt.excluded.beat_at},
            )
        )


@dataclass(frozen=True, slots=True)
class OpsSnapshot:
    outbox_pending: int = 0
    outbox_oldest_pending_seconds: float = 0.0
    outbox_failed_attempts: int = 0
    heartbeat_age_seconds: dict[str, float] = field(default_factory=dict)
    observations: int = 0
    quarantined_rows: int = 0
    runs: dict[str, int] = field(default_factory=dict)
    results: dict[str, int] = field(default_factory=dict)
    investigations: dict[str, int] = field(default_factory=dict)
    investigation_budget_exhausted: int = 0
    investigation_tokens: int = 0
    review_results: dict[str, int] = field(default_factory=dict)
    cases: dict[str, int] = field(default_factory=dict)
    human_queue_oldest_seconds: float = 0.0
    pending_recommendations: int = 0
    decision_denials: dict[str, int] = field(default_factory=dict)
    mcp_tool_calls: dict[tuple[str, str], int] = field(default_factory=dict)


def _age(now: datetime, value: datetime | None) -> float:
    return max(0.0, (now - value).total_seconds()) if value is not None else 0.0


def _grouped(conn: Connection, column: object, table: object) -> dict[str, int]:
    rows = conn.execute(select(column, func.count()).select_from(table).group_by(column))  # type: ignore[call-overload]
    return {str(k): int(v) for k, v in rows}


def snapshot(engine: Engine, now: datetime) -> OpsSnapshot:
    since = now - AUDIT_WINDOW
    with engine.connect() as conn:
        pending, oldest, attempts = conn.execute(
            select(
                func.count(),
                func.min(outbox.c.occurred_at),
                func.coalesce(func.sum(outbox.c.attempts), 0),
            ).where(outbox.c.published_at.is_(None))
        ).one()
        beats = {
            str(service): _age(now, beat_at)
            for service, beat_at in conn.execute(
                select(service_heartbeats.c.service, service_heartbeats.c.beat_at)
            )
        }
        exhausted, tokens = conn.execute(
            select(
                func.count().filter(
                    text("jsonb_array_length(coalesce(record->'budget'->'exhausted', '[]')) > 0")
                ),
                func.coalesce(func.sum(text("coalesce((record->'budget'->>'tokens')::int, 0)")), 0),
            ).select_from(investigations)
        ).one()
        reviews = {
            str(k): int(v)
            for k, v in conn.execute(
                text(
                    "SELECT record->'draft'->'review_result'->>'result' AS r, count(*) "
                    "FROM recon.investigations "
                    "WHERE record->'draft'->'review_result' IS NOT NULL GROUP BY r"
                )
            )
        }
        queue_oldest, queue_pending = conn.execute(
            select(func.min(recommendations.c.created_at), func.count()).where(
                recommendations.c.status == "PENDING"
            )
        ).one()
        denied = {
            str(k): int(v)
            for k, v in conn.execute(
                select(audit_entries.c.outcome, func.count())
                .where(
                    audit_entries.c.action == DECISION_DENIED,
                    audit_entries.c.occurred_at > since,
                )
                .group_by(audit_entries.c.outcome)
            )
        }
        tool_calls = {
            (str(action).removeprefix("mcp."), str(outcome)): int(n)
            for action, outcome, n in conn.execute(
                select(audit_entries.c.action, audit_entries.c.outcome, func.count())
                .where(
                    audit_entries.c.resource_type == "mcp_tool",
                    audit_entries.c.occurred_at > since,
                )
                .group_by(audit_entries.c.action, audit_entries.c.outcome)
            )
        }
        return OpsSnapshot(
            outbox_pending=int(pending),
            outbox_oldest_pending_seconds=_age(now, oldest),
            outbox_failed_attempts=int(attempts),
            heartbeat_age_seconds=beats,
            observations=int(conn.execute(select(func.count()).select_from(observations)).one()[0]),
            quarantined_rows=int(
                conn.execute(select(func.count()).select_from(rejections)).one()[0]
            ),
            runs=_grouped(conn, runs.c.status, runs),
            results=_grouped(conn, results.c.match_status, results),
            investigations=_grouped(conn, investigations.c.state, investigations),
            investigation_budget_exhausted=int(exhausted),
            investigation_tokens=int(tokens),
            review_results=reviews,
            cases=_grouped(conn, cases.c.status, cases),
            human_queue_oldest_seconds=_age(now, queue_oldest),
            pending_recommendations=int(queue_pending),
            decision_denials=denied,
            mcp_tool_calls=tool_calls,
        )
