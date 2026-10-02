"""Ruleset versions: rules/v1 (default) and the SYNTHETIC rules/v2 used by the rollback drill."""

from __future__ import annotations

from pathlib import Path

import pytest

from recon_domain.oracle import expected, run_files
from recon_domain.reconciliation import RULESET_VERSION, RULESETS, ruleset

DATASET = Path(__file__).resolve().parents[2] / "datasets" / "synthetic" / "transactions-v2"
FILES = {p.name: p.read_text(encoding="utf-8") for p in DATASET.glob("*.csv")}


def test_default_is_v1_and_matches_the_labels() -> None:
    assert RULESET_VERSION == "rules/v1"
    assert run_files(FILES) == expected(FILES)


def test_v2_only_drops_weak_ranking() -> None:
    v1, v2 = run_files(FILES), run_files(FILES, version="rules/v2")
    changed = {ref for ref in v1 if v1[ref] != v2[ref]}
    assert changed, "the drill needs an observable difference"
    assert {v1[ref].match_status for ref in changed} == {"PROBABLE"}
    assert {v2[ref].match_status for ref in changed} == {"UNMATCHED"}
    assert not any(c.match_status == "PROBABLE" for c in v2.values())


def test_unknown_ruleset_is_refused() -> None:
    assert set(RULESETS) == {"rules/v1", "rules/v2"}
    assert "SYNTHETIC" in ruleset("rules/v2").description
    with pytest.raises(ValueError, match="unknown ruleset"):
        ruleset("rules/v9")
