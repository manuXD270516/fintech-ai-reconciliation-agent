"""M9 fault-injection helpers, run inside the smoke container (not collected by pytest).

    python -m tests.integration.fault_injection poison <tenant>
    python -m tests.integration.fault_injection dead-letter <tenant> [event_id source_record_id]
    python -m tests.integration.fault_injection artifacts <tenant>
    python -m tests.integration.fault_injection dlq-audit <tenant>
    python -m tests.integration.fault_injection forbidden-tool <tenant>
    python -m tests.integration.fault_injection backlog|clear-backlog <recommendation_id>

Every command prints one JSON line. Data is synthetic and scoped to a drill tenant.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select, update

from recon_domain.observation import SourceKind
from recon_store.engine import runtime_engine, runtime_url
from recon_store.tables import artifacts, audit_entries, observations, recommendations
from recon_worker.runner import DLQ_PREFIX, INGEST_CONSUMER, ingest_subject

from .support import nats_connect, settings

DATASET = Path(__file__).resolve().parents[2] / "datasets" / "synthetic" / "transactions-v2"


def _engine() -> Any:
    s = settings()
    return runtime_engine(
        runtime_url(s.db_host, s.db_port, s.db_name, s.db_user, s.db_password.get_secret_value())
    )


def _record(tenant: str) -> dict[str, str]:
    text = (DATASET / "provider_report.csv").read_text(encoding="utf-8")
    row = next(r for r in csv.DictReader(io.StringIO(text)) if r["provider_id"] == "prov-alfa")
    return dict(row, tenant_id=tenant, source_record_id=f"drill-{uuid.uuid4().hex[:12]}")


async def poison(tenant: str) -> dict[str, Any]:
    nc = await nats_connect()
    try:
        await nc.jetstream().publish(
            ingest_subject(tenant, SourceKind.PROVIDER_REPORT, "prov-alfa"),
            json.dumps({"event_id": "not-a-uuid", "record": {}}).encode(),
            timeout=5,
        )
    finally:
        await nc.drain()
    return {"published": "poison"}


async def dead_letter(
    tenant: str, event_id: str | None = None, source_record_id: str | None = None
) -> dict[str, Any]:
    """Simulates a valid event that exhausted its deliveries during a dependency outage.

    Passing the ids of a previous letter recreates the *same* event (a second DLQ copy).
    """
    subject = ingest_subject(tenant, SourceKind.PROVIDER_REPORT, "prov-alfa")
    record = _record(tenant)
    if source_record_id:
        record["source_record_id"] = source_record_id
    event = {"event_id": event_id or str(uuid.uuid4()), "record": record}
    letter = {
        "subject": subject,
        "reason": "exhausted: OperationalError (synthetic fault-injection drill)",
        "data": json.dumps(event, separators=(",", ":")),
    }
    nc = await nats_connect()
    try:
        await nc.jetstream().publish(
            f"{DLQ_PREFIX}.{INGEST_CONSUMER}", json.dumps(letter).encode(), timeout=5
        )
    finally:
        await nc.drain()
    return {"event_id": event["event_id"], "source_record_id": record["source_record_id"]}


def artifact_counts(tenant: str) -> dict[str, Any]:
    engine = _engine()
    try:
        with engine.connect() as conn:
            arts = conn.execute(
                select(func.count()).select_from(artifacts).where(artifacts.c.tenant_id == tenant)
            ).scalar_one()
            obs = conn.execute(
                select(func.count())
                .select_from(observations)
                .where(observations.c.tenant_id == tenant)
            ).scalar_one()
    finally:
        engine.dispose()
    return {"artifacts": int(arts), "observations": int(obs)}


def dlq_audit(tenant: str) -> dict[str, Any]:
    engine = _engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(audit_entries.c.action, audit_entries.c.actor, audit_entries.c.outcome)
                .where(
                    audit_entries.c.tenant_id == tenant,
                    audit_entries.c.action.like("dlq.%"),
                )
                .order_by(audit_entries.c.id)
            ).all()
    finally:
        engine.dispose()
    return {"entries": [{"action": a, "actor": b, "outcome": c} for a, b, c in rows]}


async def forbidden_tool(tenant: str) -> dict[str, Any]:
    """A service identity without `knowledge:read` calls a knowledge tool (audited refusal)."""
    from recon_agents.tool_client import stdio_tool_client  # noqa: PLC0415

    async with stdio_tool_client("svc-drill-forbidden", tenant, "transactions:read") as tools:
        outcome = await tools.call("search_provider_docs", {"query": "E17 captura"})
    return {"ok": outcome.ok, "error_code": outcome.error_code}


def backlog(recommendation_id: str, hours: float = 25.0) -> dict[str, Any]:
    """Copy a pending recommendation with created_at `hours` in the past (HumanBacklog drill).

    Uses only the runtime role's INSERT grant; the copy is clearly marked in its rationale.
    """
    engine = _engine()
    try:
        with engine.begin() as conn:
            stmt = select(recommendations).where(
                recommendations.c.id == uuid.UUID(recommendation_id)
            )
            src = conn.execute(stmt).mappings().one()
            copy_id = uuid.uuid4()
            row = dict(src) | {
                "id": copy_id,
                "status": "PENDING",
                "rationale": "DRILL: copia antedatada para disparar HumanBacklog",
                "created_at": datetime.now(UTC) - timedelta(hours=hours),
            }
            conn.execute(insert(recommendations).values(**row))
    finally:
        engine.dispose()
    return {"backdated_recommendation_id": str(copy_id)}


def clear_backlog(recommendation_id: str) -> dict[str, Any]:
    """Resolve the drill copy (status only: the role cannot rewrite anything else)."""
    engine = _engine()
    try:
        with engine.begin() as conn:
            changed = conn.execute(
                update(recommendations)
                .where(recommendations.c.id == uuid.UUID(recommendation_id))
                .values(status="SUPERSEDED")
            ).rowcount
    finally:
        engine.dispose()
    return {"superseded": changed}


def main(argv: list[str]) -> int:
    command, tenant = argv[0], argv[1]
    if command == "poison":
        result = asyncio.run(poison(tenant))
    elif command == "dead-letter":
        result = asyncio.run(dead_letter(tenant, *argv[2:4]))
    elif command == "artifacts":
        result = artifact_counts(tenant)
    elif command == "dlq-audit":
        result = dlq_audit(tenant)
    elif command == "forbidden-tool":
        result = asyncio.run(forbidden_tool(tenant))
    elif command == "backlog":
        result = backlog(tenant, *(float(h) for h in argv[2:3]))  # recommendation id [hours]
    elif command == "clear-backlog":
        result = clear_backlog(tenant)  # argument: recommendation id
    else:
        print(json.dumps({"error": f"unknown command {command}"}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
