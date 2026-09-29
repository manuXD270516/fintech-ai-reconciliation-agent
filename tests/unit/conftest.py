from __future__ import annotations

import asyncio
import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from recon_api.app import create_app
from recon_api.logs import configure_logging
from recon_api.readiness import CheckStatus, ReadinessChecker

CANARY_SECRET = "canary-Zq81-must-never-appear"

VALID_ENV = {
    "APP_DB_HOST": "db.invalid",
    "APP_DB_NAME": "recon_m0",
    "APP_DB_USER": "recon_app",
    "APP_DB_PASSWORD": CANARY_SECRET,
    "APP_NATS_URL": "nats://bus.invalid:4222",
    "APP_NATS_USER": "recon_app",
    "APP_NATS_PASSWORD": CANARY_SECRET,
}


class FakeProbe:
    """Controllable probe: ok, fail, raise or hang (ignoring cancellation if asked)."""

    def __init__(self, name: str, covers: tuple[str, ...]) -> None:
        self.name = name
        self.covers = covers
        self.mode = "ok"

    async def run(self) -> dict[str, CheckStatus]:
        if self.mode == "raise":
            raise ConnectionError(f"connect failed password={CANARY_SECRET}")
        if self.mode == "hang":
            await asyncio.sleep(3600)
        if self.mode == "slow_cancel":
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                await asyncio.sleep(2)
                return dict.fromkeys(self.covers, "fail")
        if self.mode == "vector_missing":
            return {"database": "ok", "vector": "fail"}
        status: CheckStatus = "ok" if self.mode == "ok" else "fail"
        return dict.fromkeys(self.covers, status)


class Harness:
    def __init__(self, deadline: float) -> None:
        self.db = FakeProbe("postgres", ("database", "vector"))
        self.bus = FakeProbe("nats", ("messaging",))
        self.app = create_app(checker=ReadinessChecker([self.db, self.bus], deadline))

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://testserver"
        )


@pytest.fixture
def harness() -> Harness:
    return Harness(deadline=0.5)


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    configure_logging("DEBUG", stream=stream)
    # The in-process test client is not part of the API under test.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    yield stream
    configure_logging("INFO")


def json_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    return dict(VALID_ENV)
