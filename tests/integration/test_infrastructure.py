"""T03: real PostgreSQL + pgvector and NATS JetStream, plus runtime role restrictions."""

from __future__ import annotations

import json
import math

import psycopg
import pytest
from nats.js.api import StorageType

from .support import admin_connect, app_connect, nats_connect, new_run_id

pytestmark = pytest.mark.integration


def test_vector_extension_supports_knn_query() -> None:
    run_id = new_run_id()
    schema = f"smoke_{run_id}"
    with admin_connect() as conn:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        assert row == ("0.8.6",)
        try:
            conn.execute(f"CREATE SCHEMA {schema}")
            conn.execute(f"CREATE TABLE {schema}.items (id int PRIMARY KEY, embedding vector(3))")
            conn.execute(
                f"INSERT INTO {schema}.items VALUES "
                "(1, '[1,0,0]'), (2, '[0,1,0]'), (3, '[0.9,0.1,0]')"
            )
            nearest = conn.execute(
                f"SELECT id FROM {schema}.items ORDER BY embedding <-> '[1,0,0]' LIMIT 2"
            ).fetchall()
            assert nearest == [(1,), (3,)]
        finally:
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


def test_runtime_role_can_use_vector_type() -> None:
    with app_connect() as conn:
        row = conn.execute("SELECT '[1,0,0]'::vector <-> '[0,1,0]'::vector").fetchone()
    assert row is not None
    assert math.isclose(float(str(row[0])), math.sqrt(2), rel_tol=1e-6)


def test_runtime_role_has_no_initialization_privileges() -> None:
    with app_connect() as conn:
        attrs = conn.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        assert attrs == (False, False, False, False, False)

        forbidden = [
            "CREATE EXTENSION IF NOT EXISTS hstore",
            "DROP EXTENSION vector",
            "CREATE SCHEMA smoke_forbidden",
            "CREATE TABLE public.smoke_forbidden (id int)",
            "CREATE ROLE smoke_forbidden",
            "CREATE DATABASE smoke_forbidden",
        ]
        for statement in forbidden:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)


async def test_jetstream_durable_publish_consume_ack() -> None:
    run_id = new_run_id()
    stream = f"SMOKE_{run_id}"
    subject = f"smoke.{run_id}.roundtrip"
    payload = json.dumps({"synthetic": True, "kind": "m0-smoke", "run": run_id}).encode()
    nc = await nats_connect()
    js = nc.jetstream()
    try:
        await js.add_stream(name=stream, subjects=[f"smoke.{run_id}.>"], storage=StorageType.FILE)
        ack = await js.publish(subject, payload, headers={"Nats-Msg-Id": f"{run_id}-1"})
        assert ack.stream == stream
        assert ack.seq == 1
        duplicate = await js.publish(subject, payload, headers={"Nats-Msg-Id": f"{run_id}-1"})
        assert duplicate.duplicate is True

        sub = await js.pull_subscribe(subject, durable="smoke-consumer", stream=stream)
        [msg] = await sub.fetch(1, timeout=5)
        assert msg.data == payload
        await msg.ack_sync()

        info = await js.consumer_info(stream, "smoke-consumer")
        assert info.num_pending == 0
        assert info.num_ack_pending == 0
        assert info.delivered.stream_seq == 1
        stream_info = await js.stream_info(stream)
        assert stream_info.config.storage == StorageType.FILE
        assert stream_info.state.messages == 1
    finally:
        await js.delete_stream(stream)
        await nc.close()
