"""M2 T05: JWT verification (RS256 + local JWKS) and role enforcement, fail closed."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import jwt
import pytest
from scripts import dev_auth

from recon_api.app import create_app
from recon_api.auth import AuthError, JwtVerifier, Role
from recon_api.readiness import ReadinessChecker

from .conftest import FakeProbe


@pytest.fixture(scope="module")
def keys(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("keys")
    dev_auth.init(path)
    return path


@pytest.fixture(scope="module")
def verifier(keys: Path) -> JwtVerifier:
    return JwtVerifier.from_file(keys / "public" / "jwks.json", dev_auth.ISSUER, dev_auth.AUDIENCE)


def _token(keys: Path, **overrides: object) -> str:
    private = (keys / "private.pem").read_bytes()
    kid = json.loads((keys / "public" / "jwks.json").read_text())["keys"][0]["kid"]
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": dev_auth.ISSUER,
        "aud": dev_auth.AUDIENCE,
        "sub": "ana",
        "tenant_id": "tenant-demo",
        "roles": ["analyst"],
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    headers = {"kid": str(claims.pop("_kid", kid))}
    return jwt.encode(claims, private, algorithm="RS256", headers=headers)


def test_valid_token_yields_principal(keys: Path, verifier: JwtVerifier) -> None:
    principal = verifier.verify(dev_auth.token("ana", ["analyst", "auditor"], key_dir=keys))
    assert principal.subject == "ana"
    assert principal.tenant_id == "tenant-demo"
    assert principal.roles == {Role.ANALYST, Role.AUDITOR}


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 60},
        {"iss": "someone-else"},
        {"aud": "other-api"},
        {"_kid": "unknown-kid"},
        {"tenant_id": "bad tenant"},
        {"roles": "analyst"},
    ],
)
def test_invalid_tokens_are_rejected(
    keys: Path, verifier: JwtVerifier, overrides: dict[str, object]
) -> None:
    with pytest.raises(AuthError):
        verifier.verify(_token(keys, **overrides))


def test_foreign_key_and_alg_none_are_rejected(verifier: JwtVerifier, tmp_path: Path) -> None:
    dev_auth.init(tmp_path)
    forged = dev_auth.token("mallory", ["supervisor"], key_dir=tmp_path)
    with pytest.raises(AuthError):
        verifier.verify(forged)
    unsigned = jwt.encode({"sub": "mallory"}, key=None, algorithm="none")  # type: ignore[arg-type]
    with pytest.raises(AuthError):
        verifier.verify(unsigned)


def test_unknown_roles_are_dropped(keys: Path, verifier: JwtVerifier) -> None:
    principal = verifier.verify(_token(keys, roles=["root", "auditor"]))
    assert principal.roles == {Role.AUDITOR}


@pytest.fixture
def app_client(verifier: JwtVerifier) -> Iterator[httpx.AsyncClient]:
    checker = ReadinessChecker([FakeProbe("db", ("database", "vector"))], 0.5)
    app = create_app(checker=checker, verifier=verifier)
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def test_missing_or_invalid_token_is_401(app_client: httpx.AsyncClient) -> None:
    async with app_client as client:
        missing = await client.get("/v1/batches/b-1")
        invalid = await client.get("/v1/batches/b-1", headers={"Authorization": "Bearer x.y.z"})
    for resp in (missing, invalid):
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"


async def test_wrong_role_is_403_before_touching_storage(
    keys: Path, app_client: httpx.AsyncClient
) -> None:
    auditor = {"Authorization": f"Bearer {_token(keys, roles=['auditor'])}"}
    analyst = {"Authorization": f"Bearer {_token(keys, roles=['analyst'])}"}
    async with app_client as client:
        ingest = await client.post(
            "/v1/artifacts",
            headers=analyst,
            json={
                "source": "provider_report",
                "provider_id": "prov-alfa",
                "idempotency_key": "k1",
                "content": "x",
            },
        )
        run = await client.post("/v1/batches/b-1/runs", headers=auditor)
        readable = await client.get("/v1/batches/b-1", headers=auditor)
    assert ingest.status_code == 403
    assert run.status_code == 403
    # Authorized, but no storage configured in this unit app: fails closed.
    assert readable.status_code == 503


async def test_no_verifier_fails_closed() -> None:
    checker = ReadinessChecker([FakeProbe("db", ("database", "vector"))], 0.5)
    app = create_app(checker=checker)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/v1/runs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 503
