"""History-wide secret scan (M9). Heuristic, dependency-free; not a replacement for a
dedicated scanner such as gitleaks or trufflehog (see docs/security-review.md).

- Every line added in any commit reachable from any ref (`git log -p --all`) is matched
  against key/token formats, plus Luhn-valid PAN candidates.
- No commit may ever have added `.env` (other than `.env.example`), `.dev-keys/` or
  `.backups/` content.

Usage: python scripts/secret_scan.py [--json report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.check_scope import _PAN_CANDIDATE, SECRET_PATTERNS, luhn_ok  # noqa: E402

PATTERNS: dict[str, re.Pattern[str]] = SECRET_PATTERNS | {
    "Anthropic key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Stripe live key": re.compile(r"\b[rs]k_live_[0-9A-Za-z]{16,}\b"),
    "JSON Web Token": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"),
    "credential in URL": re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@'\"{}$]{6,}@"),
}
FORBIDDEN_PATHS = re.compile(r"^(\.env(?!\.example$)(\..*)?|\.dev-keys/.*|\.backups/.*)$")
SKIP_FILES = {"uv.lock", "package-lock.json"}


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True)  # fmt: skip
    return proc.stdout


def scan_history() -> dict[str, object]:
    commits = git("rev-list", "--all").split()
    findings: list[dict[str, str]] = []
    for path in sorted(set(git("log", "--all", "--name-only", "--format=").split())):
        if FORBIDDEN_PATHS.match(path):
            findings.append({"commit": "*", "file": path, "finding": "forbidden path in history"})
    commit, current = "", ""
    seen: set[tuple[str, str]] = set()
    for line in git("log", "--all", "-p", "--no-color", "--format=commit %h").splitlines():
        if line.startswith("commit "):
            commit = line.split()[1]
        elif line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else ""
        elif line.startswith("+") and current and Path(current).name not in SKIP_FILES:
            added = line[1:]
            labels = [label for label, pattern in PATTERNS.items() if pattern.search(added)]
            for match in _PAN_CANDIDATE.finditer(added):
                digits = re.sub(r"\D", "", match.group())
                if 13 <= len(digits) <= 19 and luhn_ok(digits):
                    labels.append("Luhn-valid PAN-like number")
                    break
            for label in labels:
                if (current, label) not in seen:  # first introduction only
                    seen.add((current, label))
                    findings.append({"commit": commit, "file": current, "finding": label})
    return {
        "kind": "MEASURED",
        "scanner": "scripts/secret_scan.py (heuristic regex + Luhn; not gitleaks/trufflehog)",
        "refs": len(git("for-each-ref", "--format=%(refname)").split()),
        "commits_scanned": len(commits),
        "patterns": [*sorted(PATTERNS), "Luhn-valid PAN-like number", "forbidden path"],
        "findings": findings,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    report = scan_history()
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    findings = report["findings"]
    if not isinstance(findings, list):
        raise TypeError("findings must be a list")
    for finding in findings:
        print(f"[FAIL] {finding['commit']} {finding['file']}: {finding['finding']}")
    print(f"secret scan: {report['commits_scanned']} commits, {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
