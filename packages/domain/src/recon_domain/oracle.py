"""In-memory ingestion + reconciliation of a labelled synthetic dataset, compared to its oracle.

Used by unit tests and evaluation suites; the persisted pipeline must produce the same
classification for the same dataset.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from recon_domain.batch import ReconciliationBatch
from recon_domain.ingestion import parse_csv, rows_to_csv
from recon_domain.observation import SourceKind, TransactionObservation
from recon_domain.reconciliation import Outcome, RejectedRef, RunInput, SnapshotItem, reconcile
from recon_domain.revisions import IngestOutcome, StoredRevision, decide

WINDOW_START = datetime(2026, 9, 1, 4, 0, tzinfo=UTC)
# The synthetic events span two La Paz business days (2026-09-01 and 2026-09-02).
WINDOW = timedelta(days=2)


def to_csv(rows: Iterable[Mapping[str, str]]) -> str:
    return rows_to_csv(rows)


@dataclass(frozen=True, slots=True)
class Classification:
    match_status: str
    discrepancies: str


def batches_for(labels: Iterable[Mapping[str, str]]) -> list[ReconciliationBatch]:
    scopes = sorted({(r["tenant_id"], r["provider_id"], r["merchant_account"]) for r in labels})
    batches = []
    for tenant, provider, account in scopes:
        for currency in ("USD", "BOB"):
            batches.append(
                ReconciliationBatch(
                    tenant_id=tenant,
                    batch_id=f"b-{provider}-{account}-{currency}",
                    provider_id=provider,
                    merchant_account=account,
                    currency=currency,
                    window_start=WINDOW_START,
                    window_end=WINDOW_START + WINDOW,
                    business_timezone="America/La_Paz",
                    source_pair=(SourceKind.INTERNAL_LEDGER, SourceKind.PROVIDER_REPORT),
                    cutoff_at=WINDOW_START + WINDOW + timedelta(hours=6),
                )
            )
    return batches


def classify(
    outcomes: Iterable[Outcome], left_refs: Mapping[int, str]
) -> dict[str, Classification]:
    """Map outcomes to the ledger payment reference used by the labels."""
    result: dict[str, Classification] = {}
    for o in outcomes:
        ref = left_refs.get(o.left_ids[0], o.payment_ref) if o.left_ids else o.payment_ref
        result[ref] = Classification(
            o.match_status.value, ",".join(t.value for t in o.discrepancy_types)
        )
    return result


def run_files(files: Mapping[str, str], now: datetime | None = None) -> dict[str, Classification]:
    labels = list(csv.DictReader(io.StringIO(files["labels.csv"])))
    received = WINDOW_START + WINDOW
    stored: dict[tuple[str, SourceKind, str], dict[int, tuple[str, TransactionObservation]]] = {}
    rejections: list[RejectedRef] = []
    for name, source in (
        ("internal_ledger.csv", SourceKind.INTERNAL_LEDGER),
        ("provider_report.csv", SourceKind.PROVIDER_REPORT),
    ):
        all_rows = list(csv.DictReader(io.StringIO(files[name])))
        for provider in sorted({r["provider_id"] for r in labels}):
            text = to_csv([r for r in all_rows if r["provider_id"] == provider])
            parsed = parse_csv(
                text,
                source=source,
                provider_id=provider,
                tenant_id=labels[0]["tenant_id"],
                received_at=received,
            )
            for _, obs in parsed.observations:
                history = stored.setdefault((obs.tenant_id, obs.source, obs.source_record_id), {})
                outcome = decide(
                    (StoredRevision(rev, h) for rev, (h, _) in history.items()),
                    obs.revision,
                    obs.raw_hash,
                )
                if outcome.persists:
                    history[obs.revision] = (obs.raw_hash, obs)
                elif outcome is IngestOutcome.CONFLICT:
                    raise AssertionError(f"unexpected conflict in dataset: {obs.key}")
            for r in parsed.rejections:
                if r.payment_ref and r.merchant_account and r.currency:
                    rejections.append(
                        RejectedRef(source, r.payment_ref, r.merchant_account, r.currency)
                    )

    snapshot: list[SnapshotItem] = []
    left_refs: dict[int, str] = {}
    for next_id, history in enumerate(stored.values(), start=1):
        obs = history[max(history)][1]
        snapshot.append(SnapshotItem(next_id, obs))
        if obs.source is SourceKind.INTERNAL_LEDGER:
            left_refs[next_id] = obs.payment_ref

    result: dict[str, Classification] = {}
    at = now or WINDOW_START + WINDOW + timedelta(days=1)
    for batch in batches_for(labels):
        outcomes = reconcile(
            RunInput(
                batch=batch,
                snapshot=tuple(snapshot),
                rejections=tuple(rejections),
                complete={SourceKind.INTERNAL_LEDGER: True, SourceKind.PROVIDER_REPORT: True},
                now=at,
            )
        )
        result.update(classify(outcomes, left_refs))
    return result


def expected(files: Mapping[str, str]) -> dict[str, Classification]:
    return {
        r["payment_ref"]: Classification(r["expected_match"], r["expected_discrepancies"])
        for r in csv.DictReader(io.StringIO(files["labels.csv"]))
    }
