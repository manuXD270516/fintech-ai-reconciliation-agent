"""npm audit gate: allowlisted advisories pass, new or expired ones fail."""

from __future__ import annotations

import json
from datetime import date

from scripts.npm_audit_gate import ALLOWLIST, advisories, evaluate

URL = "https://github.com/advisories/"
BRACES = {"source": 1, "name": "braces", "severity": "high", "url": URL + "GHSA-vfj7-8cjw-p6xm"}
MODERATE = {"source": 2, "name": "left-pad", "severity": "moderate", "url": URL + "GHSA-mod"}
REPORT = {
    "vulnerabilities": {
        "braces": {"via": [BRACES]},
        "micromatch": {"via": ["braces"]},
        "left-pad": {"via": [MODERATE]},
    }
}
ENTRY = {"id": "GHSA-vfj7-8cjw-p6xm", "expires": "2026-12-31"}


def test_only_blocking_direct_advisories_are_collected() -> None:
    assert advisories(REPORT) == {"GHSA-vfj7-8cjw-p6xm": ("braces", "high")}


def test_allowlisted_advisory_passes_until_it_expires() -> None:
    found = advisories(REPORT)
    assert evaluate(found, [ENTRY], date(2026, 12, 31)) == []
    [expired] = evaluate(found, [ENTRY], date(2027, 1, 1))
    assert "expired 2026-12-31" in expired


def test_new_advisory_fails() -> None:
    found = {"GHSA-new-one": ("lodash", "critical")}
    [problem] = evaluate(found, [ENTRY], date(2026, 10, 3))
    assert problem.startswith("GHSA-new-one (lodash, critical) is not in the allowlist")


def test_every_allowlist_entry_is_justified_and_dated() -> None:
    for entry in json.loads(ALLOWLIST.read_text(encoding="utf-8"))["accepted"]:
        assert entry["reason"].strip() and entry["package"]
        assert date.fromisoformat(entry["accepted_on"]) <= date.fromisoformat(entry["expires"])
