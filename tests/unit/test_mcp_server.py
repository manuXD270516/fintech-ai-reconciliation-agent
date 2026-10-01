"""M4 T01-T06: fintech-mcp-server contracts, authorization, errors, limits and transports.

Uses the in-memory fixture backend (no database). The real SQL backend and the MCP
database role are covered by tests/integration/test_mcp_sql.py.
"""

from __future__ import annotations

import copy
import functools
import inspect
import json
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError

from recon_mcp.backend import MemoryBackend
from recon_mcp.contracts import CATALOG, PROTOCOL_VERSION, Scope
from recon_mcp.identity import IdentityError, ServiceIdentity
from recon_mcp.server import build_server
from recon_mcp.tools import Limits, ToolService

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mcp_fixture.json"
TX1, TX2, TX3 = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
)
OTHER_TENANT_TX = "44444444-4444-4444-8444-444444444444"
RUN = "55555555-5555-4555-8555-555555555555"
ALL_SCOPES = frozenset(Scope)


def _service(
    scopes: frozenset[Scope] = ALL_SCOPES, limits: Limits | None = None
) -> tuple[ToolService, MemoryBackend]:
    backend = MemoryBackend(json.loads(FIXTURE.read_text(encoding="utf-8")))
    identity = ServiceIdentity("svc-investigator", "tenant-demo", scopes)
    return ToolService(backend, identity, limits, cursor_key=b"k" * 32), backend


class Session:
    def __init__(self, client: Client, service: ToolService, backend: MemoryBackend) -> None:
        self.client, self.service, self.backend = client, service, backend

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.call_tool(name, args)
        assert result.structured_content is not None
        payload: dict[str, Any] = copy.deepcopy(result.structured_content)
        payload["_is_error"] = result.is_error
        return payload


@asynccontextmanager
async def open_session() -> AsyncIterator[Session]:
    # Opened inside each test: anyio cancel scopes must enter and exit in the same task.
    service, backend = _service()
    async with Client(build_server(service), mode="legacy") as client:
        yield Session(client, service, backend)


def with_session(fn: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
    """Run the test body inside an open in-memory MCP session (same task as the test)."""
    signature = inspect.signature(fn)
    params = [p for name, p in signature.parameters.items() if name != "session"]

    @functools.wraps(fn)
    async def wrapper(**kwargs: Any) -> None:
        async with open_session() as session:
            await fn(session, **kwargs)

    wrapper.__signature__ = signature.replace(parameters=params)  # type: ignore[attr-defined]
    return wrapper


def _closed_objects(schema: Any) -> bool:
    if isinstance(schema, dict):
        if "properties" in schema and schema.get("additionalProperties") is not False:
            return False
        return all(_closed_objects(v) for v in schema.values())
    if isinstance(schema, list):
        return all(_closed_objects(v) for v in schema)
    return True


@with_session
async def test_discovery_exposes_exactly_six_read_tools(session: Session) -> None:
    tools = (await session.client.list_tools()).tools
    assert [t.name for t in tools] == list(CATALOG)
    assert len(tools) == 6
    for tool in tools:
        assert tool.annotations is not None and tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.output_schema is not None
        assert _closed_objects(tool.input_schema) and _closed_objects(tool.output_schema)
        assert not {"tenant_id", "scopes", "subject"} & set(tool.input_schema["properties"])
    names = " ".join(t.name for t in tools)
    for forbidden in ("approve", "resolve", "adjust", "execute", "write", "propose"):
        assert forbidden not in names


@with_session
async def test_protocol_revision_is_negotiated(session: Session) -> None:
    assert session.client.protocol_version == PROTOCOL_VERSION
    info = session.client.server_info
    assert info is not None and info.name == "fintech-mcp-server"


@with_session
async def test_get_transaction_current_and_historical_revisions(session: Session) -> None:
    current = await session.call("get_transaction", {"transaction_id": TX1})
    assert not current["_is_error"]
    assert current["data"]["revision"] == current["data"]["current_revision"] == 2
    assert current["provenance"][0]["locator"] == "internal_ledger/led-000001@2"
    assert current["provenance"][0]["synthetic"] is True
    assert "raw_hash" not in current["data"]
    old = await session.call("get_transaction", {"transaction_id": TX1, "revision": 1})
    assert old["data"]["status"] == "pending"
    assert old["warnings"] == ["revision 1 is not current (2)"]


@pytest.mark.parametrize(
    "args",
    [
        {"transaction_id": "not-a-uuid"},
        {"transaction_id": TX1, "revision": 0},
        {"transaction_id": TX1, "tenant_id": "tenant-other"},
        {},
    ],
)
@with_session
async def test_invalid_arguments_are_structured_errors(
    session: Session, args: dict[str, Any]
) -> None:
    out = await session.call("get_transaction", args)
    assert out["_is_error"] and out["error"]["code"] == "INVALID_ARGUMENT"
    assert out["error"]["retryable"] is False and out["error"]["correlation_id"]


@with_session
async def test_other_tenant_resources_are_indistinguishable_from_missing(session: Session) -> None:
    foreign = await session.call("get_transaction", {"transaction_id": OTHER_TENANT_TX})
    missing = await session.call(
        "get_transaction", {"transaction_id": "99999999-9999-4999-8999-999999999999"}
    )
    assert foreign["error"]["code"] == missing["error"]["code"] == "NOT_FOUND"
    assert foreign["error"]["message"] == missing["error"]["message"]
    batch = await session.call("get_reconciliation_batch", {"batch_id": "b-secret"})
    assert batch["error"]["code"] == "NOT_FOUND"
    related = await session.call("find_related_transactions", {"transaction_id": TX1})
    assert OTHER_TENANT_TX not in {c["transaction_id"] for c in related["data"]["candidates"]}


@with_session
async def test_related_candidates_pagination_and_cursor_binding(session: Session) -> None:
    out = await session.call("find_related_transactions", {"transaction_id": TX1})
    by_id = {c["transaction_id"]: c["relations"] for c in out["data"]["candidates"]}
    assert by_id == {TX2: ["same_reference"], TX3: ["amount_and_time"]}
    assert "not matches" in out["data"]["note"]
    only_ref = await session.call(
        "find_related_transactions", {"transaction_id": TX1, "relation_types": ["same_reference"]}
    )
    assert [c["transaction_id"] for c in only_ref["data"]["candidates"]] == [TX2]

    first = await session.call("find_related_transactions", {"transaction_id": TX1, "limit": 1})
    cursor = first["next_cursor"]
    assert cursor and len(first["data"]["candidates"]) == 1
    second = await session.call(
        "find_related_transactions", {"transaction_id": TX1, "limit": 1, "cursor": cursor}
    )
    assert second["next_cursor"] is None
    seen = first["data"]["candidates"] + second["data"]["candidates"]
    assert {c["transaction_id"] for c in seen} == {TX2, TX3}

    tampered = cursor[:-1] + ("0" if cursor[-1] != "0" else "1")
    bad = await session.call(
        "find_related_transactions", {"transaction_id": TX1, "cursor": tampered}
    )
    assert bad["error"]["code"] == "INVALID_ARGUMENT"
    other_args = await session.call(
        "find_related_transactions", {"transaction_id": TX2, "cursor": cursor}
    )
    assert other_args["error"]["code"] == "INVALID_ARGUMENT"
    session.backend.data["snapshot"]["transactions"] = "fixture-tx-2"
    stale = await session.call(
        "find_related_transactions", {"transaction_id": TX1, "limit": 1, "cursor": cursor}
    )
    assert stale["error"]["code"] == "STALE_SNAPSHOT"


@with_session
async def test_batch_with_run_results_and_completeness_warning(session: Session) -> None:
    out = await session.call("get_reconciliation_batch", {"batch_id": "b-alfa-01-usd", "limit": 2})
    assert out["data"]["run"]["run_id"] == RUN and out["data"]["run"]["result_count"] == 3
    assert [r["ordinal"] for r in out["data"]["results"]] == [1, 2]
    assert out["next_cursor"] and out["snapshot_version"] == "f00d"
    assert any("completeness not confirmed" in w for w in out["warnings"])
    nxt = await session.call(
        "get_reconciliation_batch",
        {"batch_id": "b-alfa-01-usd", "limit": 2, "cursor": out["next_cursor"]},
    )
    assert [r["ordinal"] for r in nxt["data"]["results"]] == [3]
    missing_run = await session.call(
        "get_reconciliation_batch",
        {"batch_id": "b-alfa-01-usd", "run_id": "66666666-6666-4666-8666-666666666666"},
    )
    assert missing_run["error"]["code"] == "NOT_FOUND"


@with_session
async def test_provider_status_is_explicit_about_validity(session: Session) -> None:
    out = await session.call(
        "get_provider_status", {"provider_id": "prov-alfa", "as_of": "2026-08-16T02:00:00+00:00"}
    )
    snap = out["data"]["snapshot"]
    assert snap["status"] == "degraded" and snap["freshness_seconds"] == 24 * 3600
    assert "not a transaction state" in out["warnings"][0]
    none = await session.call(
        "get_provider_status", {"provider_id": "prov-alfa", "as_of": "2026-01-01T00:00:00+00:00"}
    )
    assert none["data"]["snapshot"] is None and none["warnings"] == ["no snapshot valid at as_of"]
    bad = await session.call("get_provider_status", {"provider_id": "prov-gamma"})
    assert bad["error"]["code"] == "INVALID_ARGUMENT"


@with_session
async def test_knowledge_search_filters_types_tenants_and_flags_injection(
    session: Session,
) -> None:
    incidents = await session.call(
        "search_incidents",
        {"query": "liquidación neta AMOUNT_MISMATCH", "provider_id": "prov-alfa"},
    )
    assert {i["document_type"] for i in incidents["data"]["items"]} == {"incident"}
    docs = await session.call(
        "search_provider_docs",
        {"query": "liquidación neta comisión caso nota portal", "provider_id": "prov-alfa"},
    )
    ids = {i["document_id"] for i in docs["data"]["items"]}
    assert "other-tenant-runbook" not in ids and "incident-inc-0815" not in ids
    evil = [i for i in docs["data"]["items"] if i["untrusted_instructions"]]
    assert evil and f"untrusted_instructions:{evil[0]['chunk_id']}" in docs["warnings"]
    assert all(p["record_or_chunk_id"] in {i["chunk_id"] for i in docs["data"]["items"]}
               for p in docs["provenance"])  # fmt: skip
    nothing = await session.call(
        "search_provider_docs", {"query": "acuerdo especial ZETA-77", "provider_id": "prov-alfa"}
    )
    assert nothing["data"]["abstained"] and nothing["data"]["items"] == []
    missing_provider = await session.call("search_provider_docs", {"query": "E21"})
    assert missing_provider["error"]["code"] == "INVALID_ARGUMENT"


async def test_missing_scope_is_forbidden() -> None:
    service, _ = _service(scopes=frozenset({Scope.TRANSACTIONS}))
    async with Client(build_server(service), mode="legacy") as client:
        result = await client.call_tool("search_incidents", {"query": "E21"})
    assert result.is_error and result.structured_content["error"]["code"] == "FORBIDDEN"


async def test_timeout_dependency_error_and_rate_limit() -> None:
    limits = Limits(calls_per_minute=3)
    limits.timeouts["get_transaction"] = 0.1
    service, backend = _service(limits=limits)
    async with Client(build_server(service), mode="legacy") as client:
        backend.delay = 0.5
        slow = await client.call_tool("get_transaction", {"transaction_id": TX1})
        backend.delay, backend.fail = 0.0, True
        down = await client.call_tool("get_provider_status", {"provider_id": "prov-alfa"})
        backend.fail = False
        await client.call_tool("get_provider_status", {"provider_id": "prov-alfa"})
        limited = await client.call_tool("get_provider_status", {"provider_id": "prov-alfa"})
    assert slow.structured_content["error"]["code"] == "TIMEOUT"
    assert slow.structured_content["error"]["retryable"] is True
    assert down.is_error and down.structured_content["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert limited.structured_content["error"]["code"] == "RATE_LIMITED"


async def test_at_most_two_concurrent_calls() -> None:
    service, backend = _service()
    backend.delay = 0.2
    async with (
        Client(build_server(service), mode="legacy") as client,
        anyio.create_task_group() as tg,
    ):
        for _ in range(5):
            tg.start_soon(client.call_tool, "get_provider_status", {"provider_id": "prov-alfa"})
    assert service.max_in_flight == 2


async def test_large_responses_drop_whole_items_and_keep_contract() -> None:
    service, _ = _service()
    args = {"query": "liquidación neta comisión caso nota portal", "provider_id": "prov-alfa"}
    async with Client(build_server(service), mode="legacy") as client:
        full = (await client.call_tool("search_provider_docs", args)).structured_content
        size = len(json.dumps(full, ensure_ascii=False).encode())
        assert len(full["data"]["items"]) == 2
        service.limits.max_bytes = size - 50
        result = await client.call_tool("search_provider_docs", args)
    out = result.structured_content
    assert not result.is_error
    assert any(w.startswith("truncated:") for w in out["warnings"])
    assert len(out["data"]["items"]) == 1
    assert len(json.dumps(out, ensure_ascii=False).encode()) <= size
    assert {p["record_or_chunk_id"] for p in out["provenance"]} == {
        i["chunk_id"] for i in out["data"]["items"]
    }


@pytest.mark.parametrize("name", ["approve_resolution", "execute_approved_action", "sql"])
@with_session
async def test_unknown_and_write_tools_are_protocol_errors(session: Session, name: str) -> None:
    with pytest.raises(MCPError, match="Unknown tool"):
        await session.client.call_tool(name, {"case_id": "x"})


@with_session
async def test_audit_records_identity_hash_and_outcome_without_arguments(session: Session) -> None:
    await session.call("search_incidents", {"query": "secreto-de-prueba liquidación"})
    await session.call("get_transaction", {"transaction_id": OTHER_TENANT_TX})
    first, second = session.backend.audits[-2:]
    assert first["actor"] == "svc-investigator" and first["tenant_id"] == "tenant-demo"
    assert len(first["args_sha256"]) == 64 and "secreto" not in json.dumps(first)
    assert second["outcome"] == "NOT_FOUND" and second["refs"] == []


def test_identity_comes_only_from_the_environment() -> None:
    env = {"MCP_SUBJECT": "svc-a", "MCP_TENANT_ID": "tenant-demo",
           "MCP_SCOPES": "transactions:read,knowledge:read"}  # fmt: skip
    identity = ServiceIdentity.from_env(env)
    assert identity.scopes == {Scope.TRANSACTIONS, Scope.KNOWLEDGE}
    for bad in ({**env, "MCP_SCOPES": "admin:write"}, {**env, "MCP_TENANT_ID": ""},
                {**env, "MCP_KNOWLEDGE_ROLES": "root"}):  # fmt: skip
        with pytest.raises(IdentityError):
            ServiceIdentity.from_env(bad)


async def test_real_stdio_transport_with_subprocess() -> None:
    env = dict(os.environ) | {
        "MCP_FIXTURE": str(FIXTURE),
        "MCP_SUBJECT": "svc-stdio",
        "MCP_TENANT_ID": "tenant-demo",
        "MCP_SCOPES": ",".join(s.value for s in Scope),
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "recon_mcp", "--backend", "fixture"], env=env
    )
    async with Client(params, mode="legacy") as client:
        assert client.protocol_version == PROTOCOL_VERSION
        assert len((await client.list_tools()).tools) == 6
        result = await client.call_tool("get_transaction", {"transaction_id": TX2})
    assert not result.is_error
    assert result.structured_content["data"]["amount_minor"] == 9900
