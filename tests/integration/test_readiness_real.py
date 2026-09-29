"""T05/T06 against real dependencies: healthy, vector missing, JetStream disabled, hang."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from recon_api.app import create_app
from recon_api.config import MAX_READY_DEADLINE_SECONDS, Settings

from .support import admin_connect, nats_connect, new_run_id, settings

pytestmark = pytest.mark.integration


async def get_ready(s: Settings) -> tuple[int, dict[str, Any], float]:
    app = create_app(s)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:
        started = time.perf_counter()
        response = await client.get("/health/ready")
        elapsed = time.perf_counter() - started
    return response.status_code, response.json(), elapsed


async def test_ready_with_real_dependencies() -> None:
    status, body, elapsed = await get_ready(settings())
    assert status == 200
    assert body["checks"] == {"database": "ok", "vector": "ok", "messaging": "ok"}
    assert elapsed <= MAX_READY_DEADLINE_SECONDS


async def test_not_ready_when_vector_extension_missing() -> None:
    dbname = f"smoke_novector_{new_run_id()}"
    with admin_connect() as conn:
        conn.execute(f"CREATE DATABASE {dbname}")
    try:
        s = settings().model_copy(update={"db_name": dbname})
        status, body, elapsed = await get_ready(s)
    finally:
        with admin_connect() as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)")
    assert status == 503
    assert body["checks"] == {"database": "ok", "vector": "fail", "messaging": "ok"}
    assert elapsed <= MAX_READY_DEADLINE_SECONDS


async def test_not_ready_when_jetstream_disabled() -> None:
    url = os.environ["SMOKE_NATS_NOJS_URL"]
    for _ in range(20):
        try:
            nc = await nats_connect(url)
        except Exception:
            await asyncio.sleep(0.5)
            continue
        assert nc.is_connected
        await nc.close()
        break
    else:
        pytest.fail("control: plain NATS without JetStream never became reachable")

    status, body, elapsed = await get_ready(settings().model_copy(update={"nats_url": url}))
    assert status == 503
    assert body["checks"] == {"database": "ok", "vector": "ok", "messaging": "fail"}
    assert elapsed <= MAX_READY_DEADLINE_SECONDS


async def _blackhole(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    await reader.read()
    writer.close()


async def blackhole_port() -> AsyncIterator[int]:
    server = await asyncio.start_server(_blackhole, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield port
    finally:
        server.close()


@pytest.mark.parametrize("dependency", ["database", "messaging"])
async def test_hung_dependency_is_bounded_by_deadline(dependency: str) -> None:
    async for port in blackhole_port():
        if dependency == "database":
            update: dict[str, Any] = {"db_host": "127.0.0.1", "db_port": port}
            expected = {"database": "timeout", "vector": "timeout", "messaging": "ok"}
        else:
            update = {"nats_url": f"nats://127.0.0.1:{port}"}
            expected = {"database": "ok", "vector": "ok", "messaging": "timeout"}
        status, body, elapsed = await get_ready(settings().model_copy(update=update))

    assert status == 503
    assert body["checks"] == expected
    assert elapsed <= MAX_READY_DEADLINE_SECONDS
