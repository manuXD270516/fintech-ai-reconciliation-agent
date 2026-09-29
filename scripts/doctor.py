"""Prerequisite diagnosis for M0 (T02). Standard library only.

Usage:  uv run python scripts/doctor.py
Exit code 0 only when every prerequisite is present in a supported version. Each
failure names the requirement and the corrective action.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON_VERSION = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
NODE_VERSION = (ROOT / ".nvmrc").read_text(encoding="utf-8").strip()
MIN_COMPOSE = (2, 24, 0)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    action: str = ""


Runner = Callable[[list[str]], tuple[int, str]]


def run(cmd: list[str]) -> tuple[int, str]:
    exe = shutil.which(cmd[0])
    if exe is None:
        return 127, f"{cmd[0]} not found on PATH"
    try:
        proc = subprocess.run(
            [exe, *cmd[1:]], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False
        )
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]} timed out"
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in match.groups()) if match else None


def required_uv() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["tool"]["uv"]["required-version"]).lstrip("=")


def check_uv(runner: Runner) -> Check:
    want = required_uv()
    code, out = runner(["uv", "--version"])
    if code != 0:
        return Check("uv", False, out, f"install uv {want}: https://docs.astral.sh/uv/")
    have = _version(out)
    ok = have is not None and ".".join(map(str, have)) == want
    return Check("uv", ok, out, "" if ok else f"install uv {want} (uv self update {want})")


def check_python() -> Check:
    have = ".".join(map(str, sys.version_info[:3]))
    ok = have == PYTHON_VERSION
    action = "" if ok else f"run through uv: uv python install {PYTHON_VERSION}; uv run ..."
    return Check("python", ok, f"{have} ({sys.executable})", action)


def check_docker(runner: Runner) -> Check:
    code, out = runner(["docker", "version", "--format", "{{json .Server}}"])
    if code == 127:
        return Check("docker", False, out, "install Docker Desktop (WSL2) or Docker Engine")
    if code != 0:
        return Check("docker", False, "daemon not reachable", "start Docker Desktop / dockerd")
    try:
        server = json.loads(out.splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return Check("docker", False, "unexpected docker output", "check the Docker installation")
    ok = server.get("Os") == "linux"
    action = "" if ok else "switch Docker Desktop to Linux containers"
    return Check("docker", ok, f"server {server.get('Version')} {server.get('Os')}", action)


def check_compose(runner: Runner) -> Check:
    code, out = runner(["docker", "compose", "version", "--short"])
    have = _version(out) if code == 0 else None
    ok = have is not None and have >= MIN_COMPOSE
    want = ".".join(map(str, MIN_COMPOSE))
    detail = out if code == 0 else "docker compose plugin not available"
    return Check("compose", ok, detail, "" if ok else f"install Docker Compose v2 >= {want}")


def check_node(runner: Runner) -> Check:
    code, out = runner(["node", "--version"])
    if code != 0:
        return Check("node", False, out, f"install Node.js {NODE_VERSION} (see .nvmrc)")
    have, want = _version(out), _version(NODE_VERSION)
    ok = have is not None and want is not None and have[0] == want[0] and have >= want
    action = "" if ok else f"install Node.js {NODE_VERSION} (see .nvmrc)"
    return Check("node", ok, out, action)


def check_openspec() -> Check:
    package = ROOT / "node_modules" / "@fission-ai" / "openspec" / "package.json"
    want = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["devDependencies"][
        "@fission-ai/openspec"
    ]
    if not package.exists():
        return Check("openspec", False, "not installed locally", "run: npm ci")
    have = json.loads(package.read_text(encoding="utf-8"))["version"]
    ok = have == want
    return Check("openspec", ok, f"local {have}", "" if ok else "run: npm ci")


def check_env_file() -> Check:
    if (ROOT / ".env").exists():
        return Check(".env", True, "present (git-ignored)")
    return Check(".env", False, "missing", "copy the synthetic example: cp .env.example .env")


def diagnose(runner: Runner = run) -> list[Check]:
    return [
        check_uv(runner),
        check_python(),
        check_docker(runner),
        check_compose(runner),
        check_node(runner),
        check_openspec(),
        check_env_file(),
    ]


def main() -> int:
    checks = diagnose()
    for c in checks:
        line = f"[{'OK' if c.ok else 'FAIL'}] {c.name}: {c.detail}"
        print(line if c.ok else f"{line}\n       action: {c.action}")
    failed = [c.name for c in checks if not c.ok]
    print("doctor: ready" if not failed else f"doctor: NOT ready ({', '.join(failed)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
