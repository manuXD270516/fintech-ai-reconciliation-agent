"""Deterministic synthetic transaction fixtures. Contains no real or card-like data.

Every payment belongs to one labelled scenario so later milestones can evaluate
ingestion and reconciliation against a known oracle.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

LABEL_VERSIONS = ("v1", "v2")
SCHEMA_VERSION = "raw-observation-csv/v1"
DATASET_ID = "transactions"
COLUMNS = (
    "tenant_id",
    "source_record_id",
    "revision",
    "provider_id",
    "merchant_account",
    "operation",
    "payment_ref",
    "attempt_ref",
    "amount",
    "currency",
    "status",
    "occurred_at",
    "received_at",
)
LABEL_COLUMNS = (
    "tenant_id",
    "provider_id",
    "merchant_account",
    "payment_ref",
    "scenario",
    "expected_match",
    "expected_discrepancies",
)

SCENARIOS = (
    "exact",
    "amount_mismatch",
    "status_mismatch",
    "missing_external",
    "missing_internal",
    "duplicate_external",
    "revision_out_of_order",
    "transport_replay",
    "invalid_precision",
    "unknown_status",
    "weak_reference",
)
EXPECTED_V1 = {
    "exact": ("EXACT", ""),
    "amount_mismatch": ("EXACT", "AMOUNT_MISMATCH"),
    "status_mismatch": ("EXACT", "STATUS_MISMATCH"),
    "missing_external": ("UNMATCHED", "MISSING_EXTERNAL"),
    "missing_internal": ("UNMATCHED", "MISSING_INTERNAL"),
    "duplicate_external": ("NOT_EVALUATED", "DUPLICATE_CANDIDATE"),
    "revision_out_of_order": ("EXACT", ""),
    "transport_replay": ("EXACT", ""),
    "invalid_precision": ("NOT_EVALUATED", "PROCESSING_ERROR"),
    "unknown_status": ("NOT_EVALUATED", "PROCESSING_ERROR"),
    "weak_reference": ("PROBABLE", ""),
}
# v2 corrects v1: a reference-linked pair with differences is not an exact match
# (invariant 4); it stays UNMATCHED with the discrepancy linking both sides.
EXPECTED_V2 = {
    **EXPECTED_V1,
    "amount_mismatch": ("UNMATCHED", "AMOUNT_MISMATCH"),
    "status_mismatch": ("UNMATCHED", "STATUS_MISMATCH"),
}
EXPECTED_BY_VERSION = {"v1": EXPECTED_V1, "v2": EXPECTED_V2}

_LEDGER_STATUS = {"ok": "POSTED", "pending": "PENDING", "failed": "FAILED"}
_PROVIDER = {
    "prov-alfa": {
        "prefix": "alf",
        "ok": "SETTLED",
        "pending": "PENDING",
        "failed": "DECLINED",
        "capture": "CAPTURE",
    },
    "prov-beta": {"prefix": "bet", "ok": "OK", "pending": "WAIT", "failed": "KO", "capture": "CAP"},
}
_LA_PAZ = timezone(timedelta(hours=-4))


@dataclass
class Dataset:
    seed: int
    version: str = "v1"
    internal: list[dict[str, str]] = field(default_factory=list)
    provider: list[dict[str, str]] = field(default_factory=list)
    labels: list[dict[str, str]] = field(default_factory=list)

    def files(self) -> dict[str, str]:
        return {
            "internal_ledger.csv": _csv(COLUMNS, self.internal),
            "provider_report.csv": _csv(COLUMNS, self.provider),
            "labels.csv": _csv(LABEL_COLUMNS, self.labels),
        }

    def manifest(self) -> dict[str, object]:
        files = self.files()
        digests = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}
        content_hash = hashlib.sha256(
            "".join(f"{n}:{d}\n" for n, d in sorted(digests.items())).encode()
        ).hexdigest()
        return {
            "dataset_id": DATASET_ID,
            "version": self.version,
            "schema_version": SCHEMA_VERSION,
            "generator": f"synthetic-transactions/{self.version}",
            "seed": self.seed,
            "data_origin": "SYNTHETIC",
            "files": digests,
            "content_hash": content_hash,
            "counts": {
                "internal": len(self.internal),
                "provider": len(self.provider),
                "payments": len(self.labels),
            },
        }


def _csv(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _amount(minor: int) -> str:
    return f"{minor // 100}.{minor % 100:02d}"


def generate(seed: int = 20260929, per_scenario: int = 4, version: str = "v1") -> Dataset:
    expected = EXPECTED_BY_VERSION[version]
    rng = random.Random(seed)  # noqa: S311 - deterministic fixtures, not cryptography
    ds = Dataset(seed=seed, version=version)
    tenant = "tenant-demo"
    base = datetime(2026, 9, 1, 8, 0, tzinfo=_LA_PAZ)
    counters = {"led": 0, "alf": 0, "bet": 0}
    n = 0

    def next_id(prefix: str) -> str:
        counters[prefix] += 1
        return f"{prefix}-{counters[prefix]:06d}"

    def row(**values: str) -> dict[str, str]:
        return {column: values.get(column, "") for column in COLUMNS}

    for scenario in SCENARIOS:
        for _ in range(per_scenario):
            n += 1
            provider_id = "prov-alfa" if n % 2 else "prov-beta"
            vocab = _PROVIDER[provider_id]
            account = f"merchant-{1 + n % 3:02d}"
            currency = "USD" if n % 4 else "BOB"
            ref = f"pay-{n:04d}"
            minor = rng.randrange(500, 500_000)
            occurred = base + timedelta(minutes=rng.randrange(0, 60 * 20))
            received = occurred + timedelta(minutes=rng.randrange(1, 90))
            common = {
                "tenant_id": tenant,
                "provider_id": provider_id,
                "merchant_account": account,
                "currency": currency,
                "occurred_at": occurred.isoformat(),
                "received_at": received.isoformat(),
            }
            ledger = row(
                **common,
                source_record_id=next_id("led"),
                revision="1",
                operation="CAPTURE",
                payment_ref=ref,
                attempt_ref=f"{ref}-a1",
                amount=_amount(minor),
                status=_LEDGER_STATUS["ok"],
            )
            prov = row(
                **common,
                source_record_id=next_id(vocab["prefix"]),
                revision="1",
                operation=vocab["capture"],
                payment_ref=ref,
                attempt_ref="",
                amount=_amount(minor),
                status=vocab["ok"],
            )
            internal_rows, provider_rows = [ledger], [prov]

            if scenario == "amount_mismatch":
                prov["amount"] = _amount(minor - 100)
            elif scenario == "status_mismatch":
                prov["status"] = vocab["failed"]
            elif scenario == "missing_external":
                provider_rows = []
            elif scenario == "missing_internal":
                internal_rows = []
            elif scenario == "duplicate_external":
                twin = dict(prov, source_record_id=next_id(vocab["prefix"]))
                provider_rows = [prov, twin]
            elif scenario == "revision_out_of_order":
                first = dict(ledger, status=_LEDGER_STATUS["pending"])
                internal_rows = [dict(ledger, revision="2"), first]
            elif scenario == "transport_replay":
                provider_rows = [prov, dict(prov)]
            elif scenario == "invalid_precision":
                prov["amount"] = _amount(minor) + "5"
            elif scenario == "unknown_status":
                prov["status"] = "UNMAPPED_STATE"
            elif scenario == "weak_reference":
                prov["payment_ref"] = f"ext-{n:04d}"
                prov["attempt_ref"] = f"{ref}-a1"

            ds.internal += internal_rows
            ds.provider += provider_rows
            match, discrepancies = expected[scenario]
            ds.labels.append(
                {
                    "tenant_id": tenant,
                    "provider_id": provider_id,
                    "merchant_account": account,
                    "payment_ref": ref,
                    "scenario": scenario,
                    "expected_match": match,
                    "expected_discrepancies": discrepancies,
                }
            )
    return ds


def manifest_json(ds: Dataset) -> str:
    return json.dumps(ds.manifest(), indent=2, sort_keys=True) + "\n"
