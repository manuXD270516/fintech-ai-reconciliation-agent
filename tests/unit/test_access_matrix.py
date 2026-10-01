"""M9 auth/ACL review: the declared route x role matrix is exactly what the API enforces.

Every `/v1` route must answer 401 without a valid token and 403 for each role outside its
set *before* touching storage; allowed roles get past authorization (503 here, because the
unit app has no storage). The matrix is the reviewed contract in docs/security-review.md.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from scripts import dev_auth

from recon_api.app import create_app
from recon_api.auth import JwtVerifier, Role
from recon_api.readiness import ReadinessChecker

from .conftest import FakeProbe
from .test_scope import HEALTH, M9_OBSERVABILITY

ID = "00000000-0000-0000-0000-000000000001"
ALL = frozenset(Role)
READ = frozenset({Role.ANALYST, Role.SUPERVISOR, Role.AUDITOR})
A, S, ING, AU = Role.ANALYST, Role.SUPERVISOR, Role.INTEGRATION, Role.AUDITOR

# (method, path template) -> roles allowed at the HTTP layer
MATRIX: dict[tuple[str, str], frozenset[Role]] = {
    ("POST", "/v1/artifacts"): frozenset({ING}),
    ("POST", "/v1/batches"): frozenset({A}),
    ("GET", "/v1/batches"): READ,
    ("GET", "/v1/batches/{batch_id}"): READ,
    ("POST", "/v1/batches/{batch_id}/sources/{source}/complete"): frozenset({ING}),
    ("POST", "/v1/batches/{batch_id}/runs"): frozenset({A}),
    ("GET", "/v1/batches/{batch_id}/runs"): READ,
    ("GET", "/v1/runs/{run_id}"): READ,
    ("GET", "/v1/runs/{run_id}/results"): READ,
    ("POST", "/v1/runs/{run_id}/results/{ordinal}/investigations"): frozenset({A}),
    ("GET", "/v1/investigations/{investigation_id}"): READ,
    ("POST", "/v1/runs/{run_id}/results/{ordinal}/cases"): frozenset({A}),
    ("GET", "/v1/cases"): READ,
    ("GET", "/v1/cases/{case_id}"): READ,
    ("POST", "/v1/cases/{case_id}/recommendations"): frozenset({A}),
    # HTTP admits read roles so the *service* can audit refused attempts; only a supervisor
    # who did not propose/request can decide (tests/integration/test_cases_flow.py, smoke).
    ("POST", "/v1/cases/{case_id}/decisions"): READ,
    ("POST", "/v1/cases/{case_id}/close"): frozenset({S}),
    ("GET", "/v1/cases/{case_id}/audit"): frozenset({AU, S}),
}
PARAMS = {
    "{batch_id}": "b-1",
    "{source}": "provider_report",
    "{run_id}": ID,
    "{ordinal}": "1",
    "{investigation_id}": ID,
    "{case_id}": ID,
}


@pytest.fixture(scope="module")
def keys(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("matrix-keys")
    dev_auth.init(path)
    return path


@pytest.fixture(scope="module")
def client_app(keys: Path) -> object:
    verifier = JwtVerifier.from_file(keys / "public" / "jwks.json", dev_auth.ISSUER,
                                     dev_auth.AUDIENCE)  # fmt: skip
    return create_app(checker=ReadinessChecker([FakeProbe("db", ("database",))], 0.5),
                      verifier=verifier)  # fmt: skip


def _url(template: str) -> str:
    for key, value in PARAMS.items():
        template = template.replace(key, value)
    return template


def test_matrix_covers_every_authenticated_route() -> None:
    from .test_scope import CATALOG  # noqa: PLC0415 - keeps the shared catalog explicit

    public = {(m, p) for p, m in HEALTH | M9_OBSERVABILITY}
    assert {(m, p) for p, m in CATALOG} - public == set(MATRIX)


@pytest.mark.parametrize(("method", "path"), sorted(MATRIX))
async def test_route_enforces_its_roles(
    keys: Path, client_app: object, method: str, path: str
) -> None:
    transport = httpx.ASGITransport(app=client_app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        anonymous = await client.request(method, _url(path))
        assert anonymous.status_code == 401
        for role in sorted(ALL):
            token = dev_auth.token(f"user-{role.value}", [role.value], key_dir=keys)
            resp = await client.request(
                method, _url(path), headers={"Authorization": f"Bearer {token}"}
            )
            if role in MATRIX[(method, path)]:
                assert resp.status_code not in (401, 403), (role, resp.text)
            else:
                assert resp.status_code == 403, (role, resp.status_code)


async def test_public_routes_expose_no_identity_or_tenant_data(client_app: object) -> None:
    transport = httpx.ASGITransport(app=client_app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "tenant" not in metrics.text and "sub=" not in metrics.text
