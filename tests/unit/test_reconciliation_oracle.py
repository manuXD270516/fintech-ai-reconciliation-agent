"""M2 T03: the pure pipeline reproduces the v2 oracle for every labelled payment."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from recon_domain.oracle import WINDOW_START, expected, run_files
from recon_domain.synthetic import generate

DATASETS = Path(__file__).resolve().parents[2] / "datasets" / "synthetic"


def _files(version: str) -> dict[str, str]:
    root = DATASETS / f"transactions-{version}"
    return {p.name: p.read_text(encoding="utf-8") for p in root.glob("*.csv")}


def test_v2_oracle_is_reproduced_exactly() -> None:
    files = _files("v2")
    got, want = run_files(files), expected(files)
    mismatches = {ref: (got.get(ref), w) for ref, w in want.items() if got.get(ref) != w}
    assert mismatches == {}
    assert len(want) == 44


def test_pipeline_is_deterministic() -> None:
    files = _files("v2")
    assert run_files(files) == run_files(files)


def test_open_window_reports_waiting_instead_of_missing() -> None:
    files = _files("v2")
    early = run_files(files, now=WINDOW_START + timedelta(hours=12))
    missing = [r for r, w in expected(files).items() if w.discrepancies.startswith("MISSING")]
    assert missing
    assert all(early[ref].discrepancies == "WAITING_SOURCE" for ref in missing)


def test_v1_labels_are_frozen_and_differ_only_on_linked_mismatches() -> None:
    v1, v2 = expected(_files("v1")), expected(_files("v2"))
    changed = {ref for ref in v1 if v1[ref] != v2[ref]}
    assert changed
    assert all(v2[ref].match_status == "UNMATCHED" for ref in changed)
    assert generate(version="v1").files()["labels.csv"] == _files("v1")["labels.csv"]
