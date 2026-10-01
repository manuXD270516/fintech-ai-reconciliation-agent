"""The agent reaches evidence only through the MCP server (no direct DB or index access)."""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    ok: bool
    payload: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False


class ToolClient(Protocol):
    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome: ...


class McpToolClient:
    """Adapter over an open `mcp.Client`; transport failures become explicit outcomes."""

    def __init__(self, client: Client, timeout: float = 10.0) -> None:
        self.client = client
        self.timeout = timeout

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        try:
            result = await self.client.call_tool(name, arguments, read_timeout_seconds=self.timeout)
        except MCPError as exc:
            return ToolOutcome(False, {"error": {"message": str(exc)[:200]}}, "PROTOCOL_ERROR")
        except TimeoutError:
            return ToolOutcome(False, {}, "TIMEOUT", retryable=True)
        payload = dict(result.structured_content or {})
        if result.is_error:
            error = payload.get("error", {})
            return ToolOutcome(
                False, payload, str(error.get("code", "ERROR")), bool(error.get("retryable"))
            )
        return ToolOutcome(True, payload)


def server_environment(
    subject: str, tenant_id: str, scopes: str, base: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Identity of the MCP process: chosen by the orchestrator, never by the model."""
    env = dict(os.environ if base is None else base)
    for key in [k for k in env if k.startswith(("APP_DB_PASSWORD", "POSTGRES_"))]:
        env.pop(key)  # the MCP server must not inherit other database credentials
    return env | {"MCP_SUBJECT": subject, "MCP_TENANT_ID": tenant_id, "MCP_SCOPES": scopes}


@asynccontextmanager
async def stdio_tool_client(
    subject: str, tenant_id: str, scopes: str, backend: str = "sql"
) -> AsyncIterator[McpToolClient]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "recon_mcp", "--backend", backend],
        env=server_environment(subject, tenant_id, scopes),
    )
    async with Client(params, mode="legacy") as client:
        yield McpToolClient(client)
