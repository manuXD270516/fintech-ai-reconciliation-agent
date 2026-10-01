"""M7 T01-T04: evaluation framework (splits, statistics, gates, regressions, labels)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from recon_evals import __main__ as runner
from recon_evals.report import (
    SuiteResult,
    apply_gates,
    load_manifest,
    regressions,
    to_json,
    to_markdown,
)
from recon_evals.stats import f1, macro, ratio, split_of, wilson
from recon_evals.suites import approval_suite, reconciliation_suite, retrieval_suite

BASELINE = Path(__file__).resolve().parents[2] / "evals" / "baselines" / "offline.json"


def test_family_split_is_deterministic_and_roughly_60_20_20() -> None:
    families = [f"fam-{i}" for i in range(3000)]
    counts = Counter(split_of(f) for f in families)
    assert [split_of(f) for f in families[:50]] == [split_of(f) for f in families[:50]]
    assert 0.56 < counts["dev"] / 3000 < 0.64
    assert 0.17 < counts["calibration"] / 3000 < 0.23
    assert 0.17 < counts["holdout"] / 3000 < 0.23


def test_statistics_report_na_instead_of_success_on_empty_denominators() -> None:
    assert wilson(0, 0) is None and ratio(1, 0) is None and f1(0, 0, 0) is None
    assert macro([None, None]) is None
    low, high = wilson(99, 100) or [0, 0]
    assert low < 0.99 < high <= 1.0


def _suite(value: float, critical: bool = True) -> SuiteResult:
    manifest = {"gates": [{"metric": "all.x", "op": ">=", "threshold": 0.9, "critical": critical}]}
    return apply_gates(SuiteResult("demo", "MEASURED", {"all": {"x": value}}, manifest))


def test_critical_gate_failure_blocks_and_non_critical_does_not() -> None:
    assert _suite(0.95).status == "PASS"
    assert _suite(0.5).status == "FAIL"
    assert _suite(0.5, critical=False).status == "PASS"
    report = to_json([_suite(0.5)], {"commit": "x", "dirty": False, "generated_utc": "t",
                                     "host": "h"})  # fmt: skip
    assert report["overall"] == "FAIL" and report["blocking_gates"][0]["metric"] == "all.x"
    assert "**FAIL**" in to_markdown(report)
    skipped = SuiteResult("db", "SKIPPED", {}, {"gates": []})
    assert skipped.status == "SKIPPED"


def test_regressions_follow_gate_direction_and_tolerance() -> None:
    def report(value: float, op: str = ">=") -> dict[str, Any]:
        return {"suites": [{"suite": "s", "label": "MEASURED", "gates": [
            {"metric": "m", "op": op, "value": value, "critical": True}]}]}  # fmt: skip

    assert regressions(report(0.95), report(0.94)) == []
    assert regressions(report(0.95), report(0.90)) == ["s:m: 0.95 -> 0.9"]
    assert regressions(report(0.0, "=="), report(1.0, "==")) == ["s:m: 0.0 -> 1.0"]
    assert regressions(report(0.10, "<="), report(0.20, "<=")) == ["s:m: 0.1 -> 0.2"]


def test_gate_command_fails_when_a_critical_gate_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    failing = {name: (lambda: _suite(0.1)) for name in runner.OFFLINE}
    monkeypatch.setattr(runner, "SUITES", failing)
    assert runner.main(["gate", "--baseline", str(BASELINE), "--out", str(tmp_path)]) == 1
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["overall"] == "FAIL"


def test_reconciliation_suite_has_no_split_leakage_and_independent_labels() -> None:
    result = apply_gates(reconciliation_suite())
    assert result.status == "PASS"
    assert result.metrics["split_leakage_families"] == 0
    assert result.metrics["all"]["n"] == 1210
    assert result.manifest["data_origin"] == "SYNTHETIC" and result.manifest["content_hash"]


def test_db_suite_is_skipped_not_faked_without_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_DB_HOST", raising=False)
    result = retrieval_suite()
    assert result.label == "SKIPPED" and result.metrics == {}


def test_approval_matrix_and_manifests_are_consistent() -> None:
    result = apply_gates(approval_suite())
    assert result.status == "PASS" and result.metrics["self_approvals_allowed"] == 0
    for suite in ("reconciliation", "retrieval", "tools", "investigation", "approval"):
        manifest = load_manifest(suite)
        assert manifest["data_origin"] == "SYNTHETIC" and manifest["gates"]


def test_committed_baseline_is_a_passing_offline_report() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert baseline["overall"] == "PASS"
    assert [s["suite"] for s in baseline["suites"]] == list(runner.OFFLINE)
    labels = {s["suite"]: s["label"] for s in baseline["suites"]}
    assert labels["investigation"] == "SIMULATED"
