"""M1 T06: versioned synthetic fixtures are deterministic, labelled and card-data free."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from scripts.check_scope import scan_secrets

from recon_domain.synthetic import COLUMNS, SCENARIOS, generate, manifest_json

DATASET = Path(__file__).resolve().parents[2] / "datasets" / "synthetic" / "transactions-v1"


def test_committed_dataset_matches_generator() -> None:
    ds = generate()
    for name, text in ds.files().items():
        assert (DATASET / name).read_text(encoding="utf-8") == text, name
    assert (DATASET / "manifest.json").read_text(encoding="utf-8") == manifest_json(ds)


def test_generation_is_deterministic_per_seed() -> None:
    assert generate().manifest() == generate().manifest()
    assert generate(seed=1).manifest()["content_hash"] != generate().manifest()["content_hash"]


def test_every_scenario_is_labelled_and_marked_synthetic() -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_origin"] == "SYNTHETIC"
    labels = list(csv.DictReader(io.StringIO((DATASET / "labels.csv").read_text("utf-8"))))
    assert {row["scenario"] for row in labels} == set(SCENARIOS)
    header = (DATASET / "internal_ledger.csv").read_text("utf-8").splitlines()[0]
    assert tuple(header.split(",")) == COLUMNS


def test_dataset_has_no_card_like_numbers() -> None:
    root = DATASET.parents[2]
    assert scan_secrets(root, sorted(DATASET.iterdir())) == []
