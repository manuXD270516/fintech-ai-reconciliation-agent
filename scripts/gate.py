"""Single entry point for the M0 quality gate, shared by local runs and CI (T10).

Usage:
    uv run python scripts/gate.py static     # everything except the Compose smoke
    uv run python scripts/gate.py all        # static + smoke
    uv run python scripts/gate.py <step>...  # any of the STEPS below, e.g. lint types

AI provider credentials are removed from the environment of every step, so the gate
proves it does not need them. Exit code is non-zero if any step fails.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
AI_ENV = re.compile(
    r"^(OPENAI|ANTHROPIC|AZURE_OPENAI|GEMINI|GOOGLE_API|COHERE|MISTRAL|GROQ|HF|HUGGINGFACE"
    r"|TOGETHER|VOYAGE|LANGCHAIN|LANGSMITH)_\w*$|_API_KEY$"
)


def openspec_bin() -> str:
    name = "openspec.cmd" if os.name == "nt" else "openspec"
    path = ROOT / "node_modules" / ".bin" / name
    if not path.exists():
        raise SystemExit("gate: local OpenSpec missing; run `npm ci`")
    return str(path)


def uv_bin() -> str:
    exe = shutil.which("uv")
    if exe is None:
        raise SystemExit("gate: uv not found on PATH; see README prerequisites")
    return exe


STEPS: dict[str, list[list[str]]] = {
    "lock": [["{uv}", "lock", "--check"]],
    "lint": [[PY, "-m", "ruff", "check", "."], [PY, "-m", "ruff", "format", "--check", "."]],
    "types": [[PY, "-m", "mypy"]],
    "test": [[PY, "-m", "pytest"]],
    "policy": [[PY, "scripts/check_scope.py"]],
    "trace": [[PY, "scripts/check_traceability.py"]],
    "openspec": [["{openspec}", "validate", "--all", "--strict", "--no-interactive"]],
    "negative": [[PY, "scripts/gate_negative.py"]],
    # M7: offline evaluation suites; critical gates and regressions vs the baseline block.
    "evals": [[PY, "-m", "recon_evals", "gate"]],
    # M8: dashboard checks (OpenAPI types in sync, tsc, Vitest, production build).
    "web": [["{npm}", "--prefix", "apps/web", "run", "check"]],
    # M9: heuristic secret scan of every commit reachable from any ref (needs full history).
    "secrets": [[PY, "scripts/secret_scan.py"]],
    "smoke": [[PY, "scripts/smoke.py"]],
}
GROUPS = {
    "static": ["lock", "lint", "types", "test", "policy", "trace", "openspec", "negative",
               "evals", "web", "secrets"],
    "all": ["lock", "lint", "types", "test", "policy", "trace", "openspec", "negative", "evals",
            "web", "secrets", "smoke"],
}  # fmt: skip


def clean_env() -> tuple[dict[str, str], list[str]]:
    removed = sorted(k for k in os.environ if AI_ENV.search(k))
    env = {k: v for k, v in os.environ.items() if k not in removed}
    return env, removed


def npm_bin() -> str:
    exe = shutil.which("npm")
    if exe is None:
        raise SystemExit("gate: npm not found on PATH; see README prerequisites")
    return exe


def resolve(cmd: list[str]) -> list[str]:
    subs = {"{uv}": uv_bin, "{openspec}": openspec_bin, "{npm}": npm_bin}
    return [subs[part]() if part in subs else part for part in cmd]


def main(argv: list[str]) -> int:
    requested = argv or ["static"]
    steps: list[str] = []
    for item in requested:
        if item in GROUPS:
            steps += GROUPS[item]
        elif item in STEPS:
            steps.append(item)
        else:
            print(f"gate: unknown step {item!r}; choose from {sorted(STEPS) + sorted(GROUPS)}")
            return 2

    env, removed = clean_env()
    if removed:
        print(f"gate: removed AI credential variables from environment: {', '.join(removed)}")

    summary: list[tuple[str, int, float]] = []
    for step in steps:
        print(f"\n=== gate: {step} ===", flush=True)
        started = time.perf_counter()
        code = 0
        for cmd in STEPS[step]:
            code = subprocess.run(resolve(cmd), cwd=ROOT, env=env, check=False).returncode
            if code != 0:
                break
        summary.append((step, code, time.perf_counter() - started))

    print("\n=== gate summary ===")
    for step, code, seconds in summary:
        print(f"{'PASS' if code == 0 else 'FAIL'}  {step:<9} exit={code} ({seconds:.1f}s)")
    return 1 if any(code for _, code, _ in summary) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
