"""T11/T13: the documentary gate rejects incomplete or dishonest changes."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from scripts.check_traceability import check_repo

ROOT = Path(__file__).resolve().parents[2]
CHANGE = "openspec/changes/bootstrap-mvp-foundation"
AC03_TAIL = re.compile(r"\| 3\.1, 3\.2 \| \w+ \| [^|\n]+ \|")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "openspec", tmp_path / "openspec")
    return tmp_path


def edit(
    repo: Path, rel: str, pattern: str | re.Pattern[str], new: str, base: str = CHANGE
) -> None:
    path = repo / base / rel
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, new, text, count=1)
    assert count == 1, f"pattern not found in {rel}: {pattern}"
    path.write_text(updated, encoding="utf-8")


def set_task(repo: Path, task: str, checked: bool, base: str = CHANGE) -> None:
    mark = "x" if checked else " "
    edit(repo, "tasks.md", rf"- \[[ x]\] {re.escape(task)} ", f"- [{mark}] {task} ", base)


def test_real_repository_is_traceable() -> None:
    assert check_repo(ROOT) == []


@pytest.mark.parametrize(
    "artifact",
    ["proposal.md", "design.md", "tasks.md", "acceptance-criteria.md", "test-strategy.md"],
)
def test_missing_artifact_fails(repo: Path, artifact: str) -> None:
    (repo / CHANGE / artifact).unlink()
    assert any(f"missing {artifact}" in e for e in check_repo(repo))


def test_missing_spec_fails(repo: Path) -> None:
    shutil.rmtree(repo / CHANGE / "specs")
    assert any("missing specs" in e for e in check_repo(repo))


def test_unknown_references_fail(repo: Path) -> None:
    edit(repo, "acceptance-criteria.md", r"\| RF-03 \| T05, T06 \| 3\.1, 3\.2 \|",
         "| RF-09 | T99 | 9.9 |")  # fmt: skip
    errors = check_repo(repo)
    assert any("unknown requirement RF-09" in e for e in errors)
    assert any("unknown test T99" in e for e in errors)
    assert any("unknown task 9.9" in e for e in errors)
    assert any("requirement RF-03 not covered" in e for e in errors)


def test_pass_without_evidence_fails(repo: Path) -> None:
    edit(repo, "acceptance-criteria.md", AC03_TAIL, "| 3.1, 3.2 | PASS | — |")
    assert any("AC03: PASS without evidence link" in e for e in check_repo(repo))


def test_pass_with_missing_evidence_file_fails(repo: Path) -> None:
    edit(repo, "acceptance-criteria.md", AC03_TAIL, "| 3.1, 3.2 | PASS | [x](evidence/nope.md) |")
    assert any("evidence not found: evidence/nope.md" in e for e in check_repo(repo))


def test_invalid_state_fails(repo: Path) -> None:
    edit(repo, "acceptance-criteria.md", AC03_TAIL, "| 3.1, 3.2 | DONE | — |")
    assert any("AC03: state 'DONE'" in e for e in check_repo(repo))


def test_checked_task_without_passing_criterion_fails(repo: Path) -> None:
    set_task(repo, "3.1", checked=True)
    edit(repo, "acceptance-criteria.md", AC03_TAIL, "| 3.1, 3.2 | PENDING | — |")
    assert any("task 3.1 checked but no PASS" in e for e in check_repo(repo))


def test_archived_incomplete_change_fails(repo: Path) -> None:
    archived = "openspec/changes/archive/2026-01-01-bootstrap-mvp-foundation"
    shutil.copytree(repo / CHANGE, repo / archived)
    set_task(repo, "1.1", checked=False, base=archived)
    errors = check_repo(repo)
    assert any("archived with unchecked task 1.1" in e for e in errors)
