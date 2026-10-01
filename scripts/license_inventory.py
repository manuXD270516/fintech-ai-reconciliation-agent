"""Third-party license inventory (M10), offline.

Python: metadata of the distributions installed from uv.lock (License-Expression, License,
classifiers). npm: the `license` field recorded in package-lock.json (root tooling and
apps/web). Flags strong copyleft (GPL/AGPL) and unknown licenses for human review; it
does not give legal advice and does not choose a license for this repository.

Usage: uv run python scripts/license_inventory.py [--json report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOCKS = {"tooling": ROOT / "package-lock.json", "web": ROOT / "apps" / "web" / "package-lock.json"}
STRONG_COPYLEFT = re.compile(r"\b(A?GPL|AGPL)(?!.*(LGPL))", re.I)
WEAK_COPYLEFT = re.compile(r"\b(LGPL|MPL|Mozilla Public License)", re.I)
WORKSPACE = re.compile(r"^(recon-|fintech-ai-reconciliation-agent$)")


def python_license(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return str(expression)
    classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or []
                   if c.startswith("License ::")]  # fmt: skip
    if classifiers:
        return " OR ".join(sorted(set(classifiers)))
    raw = (meta.get("License") or "").strip()
    return raw.splitlines()[0][:80] if raw else "UNKNOWN"


def python_inventory() -> list[dict[str, str]]:
    locked = set(re.findall(r'^name = "([^"]+)"', (ROOT / "uv.lock").read_text("utf-8"), re.M))
    rows = []
    for dist in metadata.distributions():
        name = str(dist.metadata["Name"])
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if normalized in locked and not WORKSPACE.match(normalized):
            rows.append({"ecosystem": "python", "name": normalized, "version": dist.version,
                         "license": python_license(dist)})  # fmt: skip
    return sorted(rows, key=lambda r: r["name"])


def npm_inventory() -> list[dict[str, str]]:
    rows = []
    for scope, lock in LOCKS.items():
        data = json.loads(lock.read_text("utf-8"))
        for path, info in data.get("packages", {}).items():
            if not path:
                continue  # the project itself
            name = path.split("node_modules/")[-1]
            rows.append({"ecosystem": f"npm:{scope}", "name": name,
                         "version": str(info.get("version", "")),
                         "license": str(info.get("license") or "UNKNOWN"),
                         "dev": str(bool(info.get("dev", False))).lower()})  # fmt: skip
    return sorted(rows, key=lambda r: (r["ecosystem"], r["name"]))


def build() -> dict[str, Any]:
    rows = python_inventory() + npm_inventory()
    review = [r for r in rows if r["license"] == "UNKNOWN" or STRONG_COPYLEFT.search(r["license"])]
    return {
        "kind": "MEASURED",
        "scope": "installed Python distributions locked in uv.lock + package-lock.json entries",
        "packages": len(rows),
        "by_license": dict(Counter(r["license"] for r in rows).most_common()),
        "needs_review": review,
        # Weak copyleft (library/file level): fine to use unmodified; listed for awareness.
        "weak_copyleft": [r for r in rows if WEAK_COPYLEFT.search(r["license"])],
        "repository_license": "none (decision pending for the owner)",
        "inventory": rows,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    report = build()
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"license inventory: {report['packages']} packages, "
          f"{len(report['needs_review'])} need review, "
          f"{len(report['weak_copyleft'])} weak copyleft")  # fmt: skip
    for row in report["needs_review"]:
        print(f"  review: {row['ecosystem']} {row['name']} {row['version']}: {row['license']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
