"""Service identity of the MCP server process.

The worker that launches the server binds it to one subject, one tenant and a set of
scopes through the environment. Tool arguments can never change them, so a model cannot
ask for another tenant or a broader scope.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from recon_mcp.contracts import Scope

_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
KNOWLEDGE_ROLES = frozenset({"analyst", "supervisor", "auditor"})


class IdentityError(ValueError):
    """The service credential is missing or invalid."""


@dataclass(frozen=True, slots=True)
class ServiceIdentity:
    subject: str
    tenant_id: str
    scopes: frozenset[Scope]
    knowledge_roles: tuple[str, ...] = ("analyst",)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ServiceIdentity:
        env = os.environ if env is None else env
        subject, tenant = env.get("MCP_SUBJECT", ""), env.get("MCP_TENANT_ID", "")
        if not _IDENT.fullmatch(subject) or not _IDENT.fullmatch(tenant):
            raise IdentityError("MCP_SUBJECT and MCP_TENANT_ID must be valid identifiers")
        try:
            scopes = frozenset(Scope(s.strip()) for s in env.get("MCP_SCOPES", "").split(",") if s)
        except ValueError:
            raise IdentityError("MCP_SCOPES contains an unknown scope") from None
        roles = tuple(r.strip() for r in env.get("MCP_KNOWLEDGE_ROLES", "analyst").split(","))
        if not roles or not set(roles) <= KNOWLEDGE_ROLES:
            raise IdentityError("MCP_KNOWLEDGE_ROLES must be analyst, supervisor or auditor")
        return cls(subject, tenant, scopes, roles)
