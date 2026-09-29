"""T09: request ID correlation between header, body and JSON log; redaction."""

from __future__ import annotations

import io
import re

import pytest

from .conftest import CANARY_SECRET, Harness, json_lines

GENERATED = re.compile(r"[0-9a-f]{32}")


def access_logs(stream: io.StringIO) -> list[dict[str, object]]:
    return [e for e in json_lines(stream) if e["logger"] == "recon_api.access"]


async def test_valid_client_request_id_is_propagated(
    harness: Harness, log_stream: io.StringIO
) -> None:
    async with harness.client() as client:
        response = await client.get("/health/ready", headers={"X-Request-ID": "smoke-123_A.b"})

    assert response.headers["X-Request-ID"] == "smoke-123_A.b"
    assert response.json()["request_id"] == "smoke-123_A.b"
    [entry] = access_logs(log_stream)
    assert entry["request_id"] == "smoke-123_A.b"
    assert entry["request_id_source"] == "client"
    assert entry["method"] == "GET"
    assert entry["path"] == "/health/ready"
    assert entry["status"] == 200
    assert isinstance(entry["duration_ms"], float)


async def test_missing_request_id_is_generated(harness: Harness, log_stream: io.StringIO) -> None:
    async with harness.client() as client:
        response = await client.get("/health/live")

    request_id = response.headers["X-Request-ID"]
    assert GENERATED.fullmatch(request_id)
    [entry] = access_logs(log_stream)
    assert entry["request_id"] == request_id
    assert entry["request_id_source"] == "generated"


@pytest.mark.parametrize(
    "malformed",
    [
        'x"}\n{"level":"CRITICAL","message":"forged"',
        "a" * 65,
        "id with spaces",
        "",
        "abc;DROP",
    ],
)
async def test_malformed_request_id_is_replaced(
    harness: Harness, log_stream: io.StringIO, malformed: str
) -> None:
    async with harness.client() as client:
        response = await client.get(
            "/health/live", headers=[(b"x-request-id", malformed.encode("latin-1"))]
        )

    request_id = response.headers["X-Request-ID"]
    assert GENERATED.fullmatch(request_id)
    raw = log_stream.getvalue()
    assert "forged" not in raw
    [entry] = access_logs(log_stream)
    assert entry["request_id"] == request_id
    assert entry["request_id_source"] == "generated"
    assert all(e["level"] != "CRITICAL" for e in json_lines(log_stream))


async def test_logs_never_contain_secrets_or_query_strings(
    harness: Harness, log_stream: io.StringIO
) -> None:
    harness.db.mode = "raise"
    harness.bus.mode = "hang"
    async with harness.client() as client:
        response = await client.get(f"/health/ready?token={CANARY_SECRET}")

    assert response.status_code == 503
    raw = log_stream.getvalue()
    assert CANARY_SECRET not in raw
    assert CANARY_SECRET not in response.text
    entries = json_lines(log_stream)
    failures = [e for e in entries if e["message"] == "probe failed"]
    assert failures == [
        {**failures[0], "probe": "postgres", "exc_type": "ConnectionError"},
    ]
    [access] = access_logs(log_stream)
    assert access["path"] == "/health/ready"
    assert access["status"] == 503
