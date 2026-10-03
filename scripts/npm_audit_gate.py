"""npm audit gate with a reviewed allowlist.

Runs `npm audit --json` for each given prefix and fails on any high or critical advisory
that is not in security/npm-audit-allowlist.json, or whose allowlist entry has expired.
Usage: python scripts/npm_audit_gate.py [PREFIX ...]   (default: the repository root)
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "security" / "npm-audit-allowlist.json"
BLOCKING = {"high", "critical"}


def advisories(report: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Map advisory id -> (package, severity) for the blocking advisories in a report."""
    found: dict[str, tuple[str, str]] = {}
    for name, vuln in report.get("vulnerabilities", {}).items():
        for via in vuln.get("via", []):
            if isinstance(via, dict) and via.get("severity") in BLOCKING:
                advisory_id = str(via.get("url", "")).rsplit("/", 1)[-1] or str(via["source"])
                found[advisory_id] = (str(via.get("name", name)), str(via["severity"]))
    return found


def evaluate(
    found: dict[str, tuple[str, str]], accepted: list[dict[str, str]], today: date
) -> list[str]:
    allowed = {entry["id"]: entry for entry in accepted}
    problems = []
    for advisory_id, (package, severity) in sorted(found.items()):
        entry = allowed.get(advisory_id)
        if entry is None:
            problems.append(f"{advisory_id} ({package}, {severity}) is not in the allowlist")
        elif date.fromisoformat(entry["expires"]) < today:
            problems.append(f"{advisory_id} ({package}) allowlist entry expired {entry['expires']}")
    return problems


def audit(prefix: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ["npm", "--prefix", str(prefix), "audit", "--json"],
        capture_output=True, text=True, encoding="utf-8", check=False,
        shell=sys.platform == "win32",
    )  # fmt: skip
    report: dict[str, Any] = json.loads(proc.stdout)
    return report


def main(argv: list[str]) -> int:
    accepted = json.loads(ALLOWLIST.read_text(encoding="utf-8"))["accepted"]
    failures = 0
    for prefix in [Path(p) for p in argv] or [ROOT]:
        found = advisories(audit(prefix))
        problems = evaluate(found, accepted, date.today())
        allowed = sorted(set(found) - {p.split(" ", 1)[0] for p in problems})
        print(f"npm audit {prefix}: {len(found)} high/critical, allowlisted {allowed or 'none'}")
        for problem in problems:
            print(f"  FAIL {problem}")
        failures += len(problems)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
