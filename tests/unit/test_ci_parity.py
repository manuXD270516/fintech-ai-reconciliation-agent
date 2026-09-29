"""T10: CI runs the same gate steps as the local gate, without AI credentials."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.gate import AI_ENV, GROUPS, STEPS

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def test_ci_runs_every_local_gate_step_in_order() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    ci_steps = re.findall(r"run: uv run python scripts/gate\.py (\w+)", text)
    assert ci_steps == GROUPS["all"]
    assert set(GROUPS["all"]) == set(STEPS)


def test_ci_declares_no_secrets_and_read_only_permissions() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text
    assert re.search(r"^permissions:\n  contents: read$", text, re.MULTILINE)


def test_actions_are_pinned_by_commit_sha() -> None:
    uses = re.findall(r"uses: (\S+)", WORKFLOW.read_text(encoding="utf-8"))
    assert uses
    assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses), uses


def test_ai_credential_variables_are_stripped() -> None:
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FOO_API_KEY"):
        assert AI_ENV.search(name)
    for name in ("PATH", "APP_DB_PASSWORD", "HOME"):
        assert not AI_ENV.search(name)
