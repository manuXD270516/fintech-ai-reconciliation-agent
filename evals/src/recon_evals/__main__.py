"""Evaluation runner.

    python -m recon_evals run --suite all|<name>[,<name>] [--out DIR]
    python -m recon_evals gate [--baseline evals/baselines/offline.json] [--out DIR]
    python -m recon_evals compare BASELINE CURRENT

`gate` runs the offline suites, fails on any critical gate and on regressions against the
committed baseline. Reports are JSON + Markdown with commit, dirty flag, host and labels.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from recon_evals.report import SuiteResult, apply_gates, regressions, to_json, to_markdown
from recon_evals.suites import (
    approval_suite,
    investigation_suite,
    reconciliation_suite,
    retrieval_suite,
    tools_suite,
)

SUITES: dict[str, Callable[[], SuiteResult]] = {
    "reconciliation": reconciliation_suite,
    "retrieval": retrieval_suite,
    "tools": lambda: asyncio.run(tools_suite()),
    "investigation": lambda: asyncio.run(investigation_suite()),
    "approval": approval_suite,
}
OFFLINE = ("reconciliation", "tools", "investigation", "approval")
DEFAULT_BASELINE = Path("evals") / "baselines" / "offline.json"


def _git(*args: str) -> str:
    try:
        proc = subprocess.run(["git", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    except OSError:
        return "unavailable"
    return proc.stdout.strip() if proc.returncode == 0 else "unavailable"


def run(names: list[str]) -> dict[str, Any]:
    started = datetime.now(UTC)
    results = [apply_gates(SUITES[name]()) for name in names]
    context = {
        "kind": "evaluation-report/v1",
        "generated_utc": started.isoformat(timespec="seconds"),
        "commit": _git("rev-parse", "--short", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
        "host": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
        "suites_requested": names,
        "seconds": round((datetime.now(UTC) - started).total_seconds(), 2),
    }
    return to_json(results, context)


def write(report: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                                     encoding="utf-8")  # fmt: skip
    (out / "report.md").write_text(to_markdown(report), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--suite", default="all")
    p_run.add_argument("--out", type=Path, default=Path("evals") / "reports" / "latest")
    p_gate = sub.add_parser("gate")
    p_gate.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    p_gate.add_argument("--out", type=Path, default=Path("evals") / "reports" / "gate")
    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("baseline", type=Path)
    p_cmp.add_argument("current", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "compare":
        found = regressions(json.loads(args.baseline.read_text("utf-8")),
                            json.loads(args.current.read_text("utf-8")))  # fmt: skip
        print("\n".join(found) or "no regressions")
        return 1 if found else 0

    if args.cmd == "gate":
        names = list(OFFLINE)
    elif args.suite == "all":
        names = list(SUITES)
    else:
        names = args.suite.split(",")
    unknown = [n for n in names if n not in SUITES]
    if unknown:
        print(f"unknown suites: {unknown}; choose from {sorted(SUITES)}")
        return 2
    report = run(names)
    write(report, args.out)
    for suite in report["suites"]:
        crit = [g for g in suite["gates"] if g["critical"]]
        print(f"{suite['status']:<7} {suite['suite']:<15} {suite['label']:<9} "
              f"critical {sum(g['passed'] for g in crit)}/{len(crit)}")  # fmt: skip
    print(f"overall: {report['overall']} (report: {args.out / 'report.md'})")
    if args.cmd == "gate":
        if not args.baseline.exists():
            print(f"baseline missing: {args.baseline}")
            return 1
        found = regressions(json.loads(args.baseline.read_text("utf-8")), report)
        for item in found:
            print(f"REGRESSION {item}")
        return 1 if found or report["overall"] != "PASS" else 0
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
