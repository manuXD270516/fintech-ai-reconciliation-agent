"""T05/T06 (contract level): liveness, readiness, failure isolation and deadline."""

from __future__ import annotations

import time

import pytest

from recon_api.config import MAX_READY_DEADLINE_SECONDS

from .conftest import CANARY_SECRET, Harness


async def test_live_and_ready_ok(harness: Harness) -> None:
    async with harness.client() as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "alive", "request_id": live.headers["X-Request-ID"]}
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "request_id": ready.headers["X-Request-ID"],
        "checks": {"database": "ok", "vector": "ok", "messaging": "ok"},
    }
    assert ready.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("probe", "mode", "expected"),
    [
        ("db", "fail", {"database": "fail", "vector": "fail", "messaging": "ok"}),
        ("db", "raise", {"database": "fail", "vector": "fail", "messaging": "ok"}),
        ("db", "vector_missing", {"database": "ok", "vector": "fail", "messaging": "ok"}),
        ("db", "hang", {"database": "timeout", "vector": "timeout", "messaging": "ok"}),
        ("bus", "fail", {"database": "ok", "vector": "ok", "messaging": "fail"}),
        ("bus", "raise", {"database": "ok", "vector": "ok", "messaging": "fail"}),
        ("bus", "hang", {"database": "ok", "vector": "ok", "messaging": "timeout"}),
    ],
)
async def test_single_dependency_failure_gives_503_and_live_stays_200(
    harness: Harness, probe: str, mode: str, expected: dict[str, str]
) -> None:
    getattr(harness, probe).mode = mode
    async with harness.client() as client:
        ready = await client.get("/health/ready")
        live = await client.get("/health/live")

    assert ready.status_code == 503
    body = ready.json()
    assert body["status"] == "not_ready"
    assert body["checks"] == expected
    assert CANARY_SECRET not in ready.text
    assert "Traceback" not in ready.text
    assert live.status_code == 200


@pytest.mark.parametrize("mode", ["hang", "slow_cancel"])
async def test_deadline_is_bounded_at_max_configured_value(mode: str) -> None:
    harness = Harness(deadline=MAX_READY_DEADLINE_SECONDS)
    harness.bus.mode = mode
    async with harness.client() as client:
        started = time.perf_counter()
        ready = await client.get("/health/ready")
        elapsed = time.perf_counter() - started

    assert ready.status_code == 503
    assert ready.json()["checks"]["messaging"] == "timeout"
    assert elapsed <= MAX_READY_DEADLINE_SECONDS + 0.25


async def test_readiness_recovers_when_dependency_returns(harness: Harness) -> None:
    harness.db.mode = "fail"
    async with harness.client() as client:
        assert (await client.get("/health/ready")).status_code == 503
        harness.db.mode = "ok"
        assert (await client.get("/health/ready")).status_code == 200
