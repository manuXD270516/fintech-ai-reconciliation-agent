"""T02 (prerequisite diagnosis) and T08 support (secret/PAN scan heuristics)."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import doctor
from scripts.check_scope import check_env_files, luhn_ok, scan_secrets

# Built at runtime so the repository secret scan does not flag this file.
SYNTHETIC_PAN = "4111" + " 1111" * 3
PRIVATE_KEY_HEADER = "-----BEGIN RSA " + "PRIVATE KEY-----"


def fake_runner(missing: set[str], outputs: dict[str, str]) -> doctor.Runner:
    def runner(cmd: list[str]) -> tuple[int, str]:
        if cmd[0] in missing:
            return 127, f"{cmd[0]} not found on PATH"
        key = " ".join(cmd[:2])
        return 0, outputs[key]

    return runner


HEALTHY = {
    "uv --version": f"uv {doctor.required_uv()} (x)",
    "docker version": '{"Os": "linux", "Version": "29.8.0"}',
    "docker compose": "5.5.1",
    "node --version": f"v{doctor.NODE_VERSION}",
}


def test_all_prerequisites_present() -> None:
    checks = {c.name: c for c in doctor.diagnose(fake_runner(set(), HEALTHY))}
    for name in ("uv", "docker", "compose", "node"):
        assert checks[name].ok, checks[name]


@pytest.mark.parametrize(
    ("missing", "name", "action"),
    [
        ({"docker"}, "docker", "install Docker"),
        ({"uv"}, "uv", "install uv"),
        ({"node"}, "node", "install Node.js"),
    ],
)
def test_missing_prerequisite_names_fix(missing: set[str], name: str, action: str) -> None:
    checks = {c.name: c for c in doctor.diagnose(fake_runner(missing, HEALTHY))}
    assert not checks[name].ok
    assert action in checks[name].action


@pytest.mark.parametrize(
    ("key", "output", "name"),
    [
        ("uv --version", "uv 0.9.0", "uv"),
        ("docker compose", "2.10.0", "compose"),
        ("docker version", '{"Os": "windows", "Version": "29.8.0"}', "docker"),
        ("node --version", "v20.11.0", "node"),
    ],
)
def test_unsupported_version_is_reported(key: str, output: str, name: str) -> None:
    checks = {c.name: c for c in doctor.diagnose(fake_runner(set(), {**HEALTHY, key: output}))}
    assert not checks[name].ok
    assert checks[name].action


def test_luhn() -> None:
    digits = SYNTHETIC_PAN.replace(" ", "")
    assert luhn_ok(digits)
    assert not luhn_ok(digits[:-1] + "2")


def test_secret_scan_flags_pan_and_keys(tmp_path: Path) -> None:
    leak = tmp_path / "leak.md"
    leak.write_text(
        f"card {SYNTHETIC_PAN}\nkey = sk-{'A' * 24}\n{PRIVATE_KEY_HEADER}\n",
        encoding="utf-8",
    )
    clean = tmp_path / "clean.md"
    clean.write_text("timestamp 20260929053324 and version 0.8.6\n", encoding="utf-8")
    errors = scan_secrets(tmp_path, [leak, clean])
    assert any("PAN-like" in e for e in errors)
    assert any("OpenAI-style key" in e for e in errors)
    assert any("private key" in e for e in errors)
    assert not any("clean.md" in e for e in errors)


def test_env_example_must_use_dev_only_placeholders(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("APP_DB_PASSWORD=hunter2\n", encoding="utf-8")
    errors = check_env_files(tmp_path, [])
    assert any("APP_DB_PASSWORD must be a 'dev-only-' placeholder" in e for e in errors)
