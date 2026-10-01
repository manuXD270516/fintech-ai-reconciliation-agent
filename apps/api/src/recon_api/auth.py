"""Bearer JWT verification against a local JWKS (OIDC-compatible claims), plus RBAC.

Development keys are generated locally by `scripts/dev_auth.py`; nothing here trusts
the client beyond a valid RS256 signature, issuer, audience and expiry.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import jwt
from fastapi import HTTPException, Request

_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
ALGORITHMS = ["RS256"]


class Role(StrEnum):
    ANALYST = "analyst"
    SUPERVISOR = "supervisor"
    AUDITOR = "auditor"
    INTEGRATION = "integration"


READ_ROLES = (Role.ANALYST, Role.SUPERVISOR, Role.AUDITOR)


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    tenant_id: str
    roles: frozenset[Role]


class AuthError(Exception):
    """Token missing, malformed, expired or not signed by a trusted key."""


class JwtVerifier:
    def __init__(self, jwks: dict[str, Any], issuer: str, audience: str) -> None:
        self._keys = {k.key_id: k for k in jwt.PyJWKSet.from_dict(jwks).keys if k.key_id}
        if not self._keys:
            raise ValueError("JWKS contains no keys with a 'kid'")
        self.issuer = issuer
        self.audience = audience

    @classmethod
    def from_file(cls, path: Path, issuer: str, audience: str) -> JwtVerifier:
        return cls(json.loads(path.read_text(encoding="utf-8")), issuer, audience)

    def verify(self, token: str) -> Principal:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            key = self._keys.get(kid) if isinstance(kid, str) else None
            if key is None:
                raise AuthError("unknown signing key")
            claims = jwt.decode(
                token,
                key=key,
                algorithms=ALGORITHMS,
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
                leeway=5,
            )
        except jwt.PyJWTError as exc:
            raise AuthError(type(exc).__name__) from None
        subject, tenant, roles = claims.get("sub"), claims.get("tenant_id"), claims.get("roles")
        if not (isinstance(subject, str) and _IDENT.fullmatch(subject)):
            raise AuthError("invalid subject")
        if not (isinstance(tenant, str) and _IDENT.fullmatch(tenant)):
            raise AuthError("invalid tenant")
        if not isinstance(roles, list):
            raise AuthError("invalid roles")
        known = frozenset(Role(r) for r in roles if r in Role.__members__.values())
        return Principal(subject, tenant, known)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def require(*roles: Role) -> Callable[[Request], Principal]:
    allowed = frozenset(roles)

    def dependency(request: Request) -> Principal:
        verifier: JwtVerifier | None = getattr(request.app.state, "verifier", None)
        if verifier is None:
            raise HTTPException(503, detail="authentication is not configured")
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise _unauthorized("missing bearer token")
        try:
            principal = verifier.verify(token.strip())
        except AuthError:
            raise _unauthorized("invalid token") from None
        if not principal.roles & allowed:
            raise HTTPException(403, detail="insufficient role")
        request.state.principal = principal
        return principal

    return dependency
