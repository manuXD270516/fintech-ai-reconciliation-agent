"""T07: invalid configuration blocks startup and never echoes secret values."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from recon_api.config import ConfigurationError, load_settings

from .conftest import CANARY_SECRET, VALID_ENV


def test_valid_configuration_loads(valid_env: dict[str, str]) -> None:
    settings = load_settings()
    assert settings.db_password.get_secret_value() == CANARY_SECRET
    assert CANARY_SECRET not in repr(settings)
    assert settings.http_host == "127.0.0.1"


@pytest.mark.parametrize(
    ("variable", "value", "expected_field"),
    [
        ("APP_DB_PASSWORD", None, "APP_DB_PASSWORD"),
        ("APP_DB_HOST", None, "APP_DB_HOST"),
        ("APP_NATS_URL", None, "APP_NATS_URL"),
        ("APP_DB_PORT", "not-a-port", "APP_DB_PORT"),
        ("APP_READY_TIMEOUT_SECONDS", "3.5", "APP_READY_TIMEOUT_SECONDS"),
        ("APP_NATS_URL", f"nats://user:{CANARY_SECRET}@bus:4222", "APP_NATS_URL"),
        ("APP_DB_PASSWORD", "short", "APP_DB_PASSWORD"),
    ],
)
def test_invalid_configuration_names_field_without_value(
    valid_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str | None,
    expected_field: str,
) -> None:
    if value is None:
        monkeypatch.delenv(variable)
    else:
        monkeypatch.setenv(variable, value)

    with pytest.raises(ConfigurationError) as info:
        load_settings()

    fields = [field for field, _ in info.value.problems]
    assert fields == [expected_field]
    rendered = str(info.value) + repr(info.value.problems)
    assert CANARY_SECRET not in rendered
    if value is not None:
        assert value not in rendered


def test_process_refuses_to_start_with_invalid_config() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("APP_")}
    env.update(VALID_ENV)
    env["APP_NATS_URL"] = f"nats://leak:{CANARY_SECRET}@bus:4222"
    del env["APP_DB_HOST"]

    proc = subprocess.run(
        [sys.executable, "-m", "recon_api"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert proc.returncode == 2
    output = proc.stdout + proc.stderr
    assert CANARY_SECRET not in output
    error = json.loads(proc.stderr.strip().splitlines()[-1])
    assert error["message"] == "invalid configuration; refusing to start"
    assert sorted(f["field"] for f in error["fields"]) == ["APP_DB_HOST", "APP_NATS_URL"]
