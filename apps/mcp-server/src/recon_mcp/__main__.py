"""Run fintech-mcp-server over stdio.

    python -m recon_mcp --backend sql       # MCP_DB_* (read-only role) + MCP_* identity
    python -m recon_mcp --backend fixture   # MCP_FIXTURE=<json> for contract tests/demos

Identity comes from MCP_SUBJECT, MCP_TENANT_ID, MCP_SCOPES and MCP_KNOWLEDGE_ROLES,
set by the process that launches the server, never from tool arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anyio
from mcp.server.stdio import stdio_server

from recon_mcp.backend import MemoryBackend, ReadBackend
from recon_mcp.identity import IdentityError, ServiceIdentity
from recon_mcp.server import build_server
from recon_mcp.tools import Limits, ToolService


def _backend(kind: str) -> ReadBackend:
    if kind == "fixture":
        return MemoryBackend.from_file(Path(os.environ["MCP_FIXTURE"]))
    from recon_mcp.sql_backend import SqlBackend  # noqa: PLC0415 - optional heavy import

    return SqlBackend.from_env(os.environ)


async def _serve(service: ToolService) -> None:
    server = build_server(service)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["sql", "fixture"], default="sql")
    args = parser.parse_args(argv)
    try:
        identity = ServiceIdentity.from_env()
        backend = _backend(args.backend)
    except (IdentityError, KeyError) as exc:
        print(json.dumps({"error": f"invalid MCP configuration: {exc}"}), file=sys.stderr)
        return 2
    key = os.environ.get("MCP_CURSOR_KEY", "").encode() or None
    anyio.run(_serve, ToolService(backend, identity, Limits(), key))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
