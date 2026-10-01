"""M10: AI kill switch refuses new investigations without touching the deterministic path."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from scripts import dev_auth

from recon_api.app import create_app
from recon_api.auth import JwtVerifier
from recon_api.metrics import parse
from recon_api.readiness import ReadinessChecker

from .conftest import VALID_ENV, FakeProbe

ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
def keys(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("kill-keys")
    dev_auth.init(path)
    return path


def _client(keys: Path, ai_enabled: bool) -> httpx.AsyncClient:
    verifier = JwtVerifier.from_file(keys / "public" / "jwks.json", dev_auth.ISSUER,
                                     dev_auth.AUDIENCE)  # fmt: skip
    app = create_app(checker=ReadinessChecker([FakeProbe("db", ("database",))], 0.5),
                     verifier=verifier, ai_enabled=ai_enabled)  # fmt: skip
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_switched_off_refuses_investigations_with_a_clear_code(keys: Path) -> None:
    analyst = {"Authorization": f"Bearer {dev_auth.token('ana', ['analyst'], key_dir=keys)}"}
    async with _client(keys, ai_enabled=False) as client:
        refused = await client.post(f"/v1/runs/{ID}/results/1/investigations", headers=analyst)
        # The deterministic path is not gated by the switch (503 here = no storage in unit app).
        run = await client.post("/v1/batches/b-1/runs", headers=analyst)
        metrics = await client.get("/metrics")
    assert refused.status_code == 503
    assert refused.json()["detail"] == {"code": "ai_disabled"}
    assert run.status_code == 503 and "ai_disabled" not in run.text
    assert parse(metrics.text)["recon_ai_enabled"] == [({}, 0.0)]


async def test_switch_still_requires_authorization_first(keys: Path) -> None:
    auditor = {"Authorization": f"Bearer {dev_auth.token('aud', ['auditor'], key_dir=keys)}"}
    async with _client(keys, ai_enabled=False) as client:
        anonymous = await client.post(f"/v1/runs/{ID}/results/1/investigations")
        wrong_role = await client.post(f"/v1/runs/{ID}/results/1/investigations", headers=auditor)
    assert (anonymous.status_code, wrong_role.status_code) == (401, 403)


def test_setting_defaults_on_and_parses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from recon_api.config import load_settings  # noqa: PLC0415

    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    assert load_settings().ai_enabled is True
    monkeypatch.setenv("APP_AI_ENABLED", "false")
    assert load_settings().ai_enabled is False
