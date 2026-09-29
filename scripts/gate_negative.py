"""Negative gate (T11): each injected defect must make its gate step fail.

Works on throwaway copies of the repository; the real tree is hashed before and after
to prove it was not mutated. An unmodified control copy must pass every step first.

Usage: uv run python scripts/gate_negative.py
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGE = Path("openspec/changes/bootstrap-mvp-foundation")
SPEC = CHANGE / "specs/repository-foundation/spec.md"
IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "node_modules", ".smoke", ".env", "*_cache", "__pycache__"
)
Mutation = Callable[[Path], None]


def _replace(rel: Path | str, old: str, new: str) -> Mutation:
    def mutate(copy: Path) -> None:
        path = copy / rel
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise RuntimeError(f"mutation anchor not found in {rel}: {old!r}")
        path.write_text(text.replace(old, new), encoding="utf-8")

    return mutate


def _regex(rel: Path, pattern: str, replacement: str) -> Mutation:
    def mutate(copy: Path) -> None:
        path = copy / rel
        original = path.read_text(encoding="utf-8")
        text, count = re.subn(pattern, replacement, original, count=1, flags=re.S)
        if count != 1:
            raise RuntimeError(f"mutation pattern not found in {rel}: {pattern!r}")
        path.write_text(text, encoding="utf-8")

    return mutate


def _delete(rel: Path) -> Mutation:
    def mutate(copy: Path) -> None:
        (copy / rel).unlink()

    return mutate


def _no_op(copy: Path) -> None:
    return None


def step_command(step: str, copy: Path) -> list[str]:
    if step == "openspec":
        name = "openspec.cmd" if os.name == "nt" else "openspec"
        return [str(ROOT / "node_modules" / ".bin" / name), "validate", "--all", "--strict",
                "--no-interactive"]  # fmt: skip
    if step == "trace":
        return [sys.executable, str(copy / "scripts" / "check_traceability.py"), str(copy)]
    if step == "contract":
        return [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                "tests/unit/test_health_contract.py", "tests/unit/test_scope.py"]  # fmt: skip
    raise ValueError(step)


@dataclass(frozen=True)
class Case:
    name: str
    mutation: Mutation
    step: str
    expect_fail: bool


CASES = [
    Case("control: openspec", _no_op, "openspec", False),
    Case("control: traceability", _no_op, "trace", False),
    Case("control: contract tests", _no_op, "contract", False),
    Case(
        "requirement RF-03 without scenarios",
        _regex(
            SPEC,
            r"(### Requirement: RF-03[^\n]*\n\n[^\n]+\n)\n#### Scenario:.*?"
            r"(?=### Requirement: RF-04)",
            r"\1\n",
        ),
        "openspec",
        True,
    ),
    Case(
        "requirement RF-03 without SHALL/MUST",
        _regex(SPEC, r"(### Requirement: RF-03[^\n]*\n\n)[^\n]+\n", r"\1La API expone salud.\n"),
        "openspec",
        True,
    ),
    Case("test-strategy.md removed", _delete(CHANGE / "test-strategy.md"), "trace", True),
    Case(
        "criterion references unknown requirement",
        _replace(CHANGE / "acceptance-criteria.md", "| RF-03 |", "| RF-99 |"),
        "trace",
        True,
    ),
    Case(
        "readiness returns 200 when a dependency fails",
        _replace(
            "apps/api/src/recon_api/app.py",
            "response.status_code = 200 if is_ready else 503",
            "response.status_code = 200",
        ),
        "contract",
        True,
    ),
    Case(
        "non-health route added",
        _replace(
            "apps/api/src/recon_api/app.py",
            "    return app\n",
            '    app.add_api_route("/payments", live, methods=["POST"])\n    return app\n',
        ),
        "contract",
        True,
    ),
]


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    skip = {".git", ".venv", "node_modules", ".smoke", ".mypy_cache", ".ruff_cache",
            ".pytest_cache", "__pycache__"}  # fmt: skip
    for path in sorted(root.rglob("*")):
        if path.is_file() and not skip.intersection(path.relative_to(root).parts):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def run_case(case: Case, workdir: Path) -> tuple[int, str]:
    copy = workdir / "repo"
    shutil.copytree(ROOT, copy, ignore=IGNORE)
    try:
        case.mutation(copy)
        env = {**os.environ, "PYTHONPATH": str(copy / "apps" / "api" / "src")}
        proc = subprocess.run(
            step_command(case.step, copy),
            cwd=copy,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        last = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
        return proc.returncode, last[0].encode("ascii", "replace").decode("ascii")
    finally:
        shutil.rmtree(copy, ignore_errors=True)


def main() -> int:
    before = tree_digest(ROOT)
    failures = 0
    with tempfile.TemporaryDirectory(prefix="m0-negative-", ignore_cleanup_errors=True) as tmp:
        for case in CASES:
            code, last_line = run_case(case, Path(tmp))
            failed = code != 0
            ok = failed == case.expect_fail
            failures += not ok
            expected = "fail" if case.expect_fail else "pass"
            print(f"[{'OK' if ok else 'WRONG'}] {case.name}: step={case.step} expected={expected} "
                  f"exit={code} :: {last_line[:120]}")  # fmt: skip
    after = tree_digest(ROOT)
    if before != after:
        print("[WRONG] real working tree changed during negative gate")
        failures += 1
    else:
        print("[OK] real working tree unchanged")
    print(f"negative gate: {'OK' if not failures else f'{failures} unexpected result(s)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
