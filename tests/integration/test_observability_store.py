"""M9: heartbeat upsert, operational snapshot and least-privilege grants on real PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from sqlalchemy import Engine, select

from recon_store.engine import runtime_engine, runtime_url
from recon_store.ops import beat, snapshot
from recon_store.tables import service_heartbeats

from .support import app_connect, new_run_id, settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    s = settings()
    eng = runtime_engine(
        runtime_url(s.db_host, s.db_port, s.db_name, s.db_user, s.db_password.get_secret_value())
    )
    yield eng
    eng.dispose()


def test_heartbeat_is_an_upsert_and_feeds_the_snapshot(engine: Engine) -> None:
    service = "it-heartbeat"  # fixed name: one row, no label growth across runs
    run = new_run_id()
    now = datetime.now(UTC)
    beat(engine, service, f"one-{run}", now - timedelta(seconds=30))
    beat(engine, service, "two", now - timedelta(seconds=5))
    with engine.connect() as conn:
        rows = conn.execute(
            select(service_heartbeats.c.instance).where(service_heartbeats.c.service == service)
        ).all()
    assert [r[0] for r in rows] == ["two"]
    snap = snapshot(engine, now)
    assert 4.0 <= snap.heartbeat_age_seconds[service] <= 6.0
    assert snap.outbox_pending >= 0 and snap.observations >= 0
    assert all(isinstance(k, tuple) and len(k) == 2 for k in snap.mcp_tool_calls)


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM recon.service_heartbeats WHERE false",
        "UPDATE recon.service_heartbeats SET service = 'x' WHERE false",
        "UPDATE recon.outbox SET trace_context = 'x' WHERE false",
        "UPDATE recon.audit_entries SET actor = 'x' WHERE false",
    ],
)
def test_runtime_role_grants_stay_minimal(statement: str) -> None:
    with app_connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)
