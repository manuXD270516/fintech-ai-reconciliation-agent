"""T04 helper: `write` a DB marker and a pending JetStream message; `verify` after restart.

Run inside the smoke container:
    python -m tests.integration.persistence write <run_id>
    python -m tests.integration.persistence verify <run_id>
Only resources named after <run_id> are created and removed.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys

from nats.aio.client import Client as NatsClient
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, StorageType
from nats.js.errors import NotFoundError

from .support import admin_connect, nats_connect

CONSUMER = "pending"


def _names(run_id: str) -> tuple[str, str, str, str]:
    if not re.fullmatch(r"[a-z0-9]{6,32}", run_id):
        raise SystemExit("run_id must be 6-32 lowercase alphanumerics")
    return f"smoke_persist_{run_id}", f"PERSIST_{run_id}", f"persist.{run_id}.msg", run_id


async def write(run_id: str) -> dict[str, object]:
    schema, stream, subject, marker = _names(run_id)
    with admin_connect() as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(f"CREATE TABLE {schema}.marker (value text NOT NULL)")
        conn.execute(f"INSERT INTO {schema}.marker VALUES (%s)", (f"synthetic-{marker}",))

    nc = await nats_connect()
    try:
        js = nc.jetstream()
        await js.add_stream(name=stream, subjects=[subject], storage=StorageType.FILE)
        ack = await js.publish(subject, json.dumps({"synthetic": True, "run": run_id}).encode())
        await js.add_consumer(
            stream,
            ConsumerConfig(
                durable_name=CONSUMER,
                ack_policy=AckPolicy.EXPLICIT,
                deliver_policy=DeliverPolicy.ALL,
            ),
        )
        num_pending = 0
        for _ in range(20):
            num_pending = (await js.consumer_info(stream, CONSUMER)).num_pending
            if num_pending == 1:
                break
            await asyncio.sleep(0.1)
    finally:
        await nc.close()
    return {"step": "write", "marker_rows": 1, "stream_seq": ack.seq, "num_pending": num_pending}


async def verify(run_id: str) -> dict[str, object]:
    schema, stream, _subject, marker = _names(run_id)
    result: dict[str, object] = {"step": "verify"}
    with admin_connect() as conn:
        rows = conn.execute(f"SELECT value FROM {schema}.marker").fetchall()
    result["marker_survived"] = rows == [(f"synthetic-{marker}",)]

    nc = await nats_connect()
    try:
        js = nc.jetstream()
        before = await js.consumer_info(stream, CONSUMER)
        result["pending_before_consume"] = before.num_pending
        sub = await js.pull_subscribe_bind(CONSUMER, stream=stream)
        [msg] = await sub.fetch(1, timeout=5)
        result["payload_ok"] = json.loads(msg.data) == {"synthetic": True, "run": run_id}
        await msg.ack_sync()
        after = await js.consumer_info(stream, CONSUMER)
        result["pending_after_ack"] = after.num_pending + after.num_ack_pending
    finally:
        await cleanup_async(run_id, nc)
    result["ok"] = (
        result["marker_survived"] is True
        and result["pending_before_consume"] == 1
        and result["payload_ok"] is True
        and result["pending_after_ack"] == 0
    )
    return result


async def cleanup_async(run_id: str, nc: NatsClient | None = None) -> None:
    schema, stream, _, _ = _names(run_id)
    with admin_connect() as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    client = nc or await nats_connect()
    try:
        await client.jetstream().delete_stream(stream)
    except NotFoundError:
        pass
    finally:
        await client.close()


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in {"write", "verify", "cleanup"}:
        print("usage: persistence.py write|verify|cleanup <run_id>", file=sys.stderr)
        return 2
    command, run_id = argv
    if command == "cleanup":
        asyncio.run(cleanup_async(run_id))
        print(json.dumps({"step": "cleanup", "ok": True}))
        return 0
    result = asyncio.run(write(run_id) if command == "write" else verify(run_id))
    print(json.dumps(result))
    if command == "write":
        return 0 if result["num_pending"] == 1 else 1
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
