"""OpenSpec traceability gate (T11/T13). Complements `openspec validate --strict`.

For every active change it requires the six artifacts, checks that each acceptance
criterion points to existing requirements, tests and tasks, that everything is covered,
that PASS/FAIL rows link existing evidence and that every checked task belongs to a
non-FAIL criterion with linked evidence. Archived changes must be fully checked and PASS.

Usage: python scripts/check_traceability.py [repo_root]
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FILES = (
    "proposal.md",
    "design.md",
    "tasks.md",
    "acceptance-criteria.md",
    "test-strategy.md",
)
STATES = {"PENDING", "PASS", "FAIL"}

_RF = re.compile(r"^### Requirement: (RF-\d+)\b", re.MULTILINE)
_T = re.compile(r"^\| (T\d+) \|", re.MULTILINE)
_TASK = re.compile(r"^- \[( |x)\] (\d+\.\d+) ", re.MULTILINE)
_LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


@dataclass(frozen=True)
class Criterion:
    ac_id: str
    requirements: tuple[str, ...]
    tests: tuple[str, ...]
    tasks: tuple[str, ...]
    state: str
    evidence: tuple[str, ...]


def _ids(cell: str, pattern: str) -> tuple[str, ...]:
    return tuple(re.findall(pattern, cell))


def parse_criteria(text: str) -> tuple[list[Criterion], list[str]]:
    errors: list[str] = []
    lines = [ln.strip() for ln in text.splitlines()]
    header_idx = next((i for i, ln in enumerate(lines) if ln.startswith("| ID |")), None)
    if header_idx is None:
        return [], ["acceptance-criteria.md: table with header '| ID |' not found"]
    headers = [h.strip() for h in lines[header_idx].strip("|").split("|")]
    needed = ["ID", "Requirements", "Tests", "Tasks", "Estado", "Evidencia"]
    missing = [h for h in needed if h not in headers]
    if missing:
        return [], [f"acceptance-criteria.md: missing columns {missing}"]
    col = {h: headers.index(h) for h in needed}
    criteria: list[Criterion] = []
    for line in lines[header_idx + 2 :]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(headers):
            errors.append(f"acceptance-criteria.md: malformed row: {line[:60]}")
            continue
        criteria.append(
            Criterion(
                ac_id=cells[col["ID"]],
                requirements=_ids(cells[col["Requirements"]], r"RF-\d+"),
                tests=_ids(cells[col["Tests"]], r"T\d+"),
                tasks=_ids(cells[col["Tasks"]], r"\d+\.\d+"),
                state=cells[col["Estado"]].strip("*"),
                evidence=tuple(_LINK.findall(cells[col["Evidencia"]])),
            )
        )
    return criteria, errors


def check_change(change: Path, archived: bool = False) -> list[str]:
    name = change.name
    errors = [f"{name}: missing {f}" for f in REQUIRED_FILES if not (change / f).is_file()]
    specs = sorted(change.glob("specs/*/spec.md"))
    if not specs:
        errors.append(f"{name}: missing specs/<capability>/spec.md")
    if errors:
        return errors

    requirements = {rf for s in specs for rf in _RF.findall(s.read_text(encoding="utf-8"))}
    tests = set(_T.findall((change / "test-strategy.md").read_text(encoding="utf-8")))
    task_marks = dict(
        (tid, mark == "x")
        for mark, tid in _TASK.findall((change / "tasks.md").read_text(encoding="utf-8"))
    )
    criteria, parse_errors = parse_criteria(
        (change / "acceptance-criteria.md").read_text(encoding="utf-8")
    )
    errors += [f"{name}: {e}" for e in parse_errors]
    if not requirements:
        errors.append(f"{name}: no '### Requirement: RF-xx' found in specs")
    if not tests:
        errors.append(f"{name}: no test IDs (| Txx |) in test-strategy.md")
    if not task_marks:
        errors.append(f"{name}: no numbered tasks in tasks.md")
    if not criteria:
        errors.append(f"{name}: no acceptance criteria rows")

    seen: set[str] = set()
    for ac in criteria:
        where = f"{name}: {ac.ac_id}"
        if ac.ac_id in seen:
            errors.append(f"{where}: duplicated ID")
        seen.add(ac.ac_id)
        for kind, refs, known in (
            ("requirement", ac.requirements, requirements),
            ("test", ac.tests, tests),
            ("task", ac.tasks, set(task_marks)),
        ):
            if not refs:
                errors.append(f"{where}: no {kind} referenced")
            errors += [f"{where}: unknown {kind} {ref}" for ref in refs if ref not in known]
        if ac.state not in STATES:
            errors.append(f"{where}: state {ac.state!r} not in {sorted(STATES)}")
        if ac.state in {"PASS", "FAIL"} and not ac.evidence:
            errors.append(f"{where}: {ac.state} without evidence link")
        for link in ac.evidence:
            if not (change / link).resolve().is_file():
                errors.append(f"{where}: evidence not found: {link}")

    for kind, known, used in (
        ("requirement", requirements, {r for ac in criteria for r in ac.requirements}),
        ("test", tests, {t for ac in criteria for t in ac.tests}),
        ("task", set(task_marks), {t for ac in criteria for t in ac.tasks}),
    ):
        errors += [f"{name}: {kind} {x} not covered by any criterion" for x in sorted(known - used)]

    evidenced_tasks = {t for ac in criteria if ac.evidence and ac.state != "FAIL" for t in ac.tasks}
    for tid, checked in task_marks.items():
        if checked and tid not in evidenced_tasks:
            errors.append(f"{name}: task {tid} checked but no criterion links evidence for it")

    if archived:
        errors += [
            f"{name}: archived with unchecked task {t}" for t, c in task_marks.items() if not c
        ]
        errors += [
            f"{name}: archived with {ac.ac_id} {ac.state}" for ac in criteria if ac.state != "PASS"
        ]
    return errors


def check_repo(root: Path) -> list[str]:
    changes_dir = root / "openspec" / "changes"
    if not changes_dir.is_dir():
        return ["openspec/changes not found"]
    errors: list[str] = []
    for change in sorted(p for p in changes_dir.iterdir() if p.is_dir() and p.name != "archive"):
        errors += check_change(change)
    archive = changes_dir / "archive"
    if archive.is_dir():
        for change in sorted(p for p in archive.iterdir() if p.is_dir()):
            errors += check_change(change, archived=True)
    return errors


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent
    errors = check_repo(root)
    for error in errors:
        print(f"[FAIL] {error}")
    print(f"traceability: {'OK' if not errors else f'{len(errors)} problem(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
