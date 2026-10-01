"""Deterministic 1:1 reconciliation rules (`rules/v1`). Pure: same input, same output.

Pipeline: batch admission -> duplicate detection -> processing errors -> strong
reference pairs (exact or linked discrepancies) -> explainable weak ranking ->
missing sides according to cutoff and source completeness.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from recon_domain.batch import ReconciliationBatch
from recon_domain.observation import OperationType, SourceKind, TransactionObservation

RULESET_VERSION = "rules/v1"
WEAK_THRESHOLD = 0.6
WEAK_WEIGHTS = {"attempt_ref": 0.6, "amount": 0.3, "time_1h": 0.1}


class MatchStatus(StrEnum):
    EXACT = "EXACT"
    PROBABLE = "PROBABLE"
    UNMATCHED = "UNMATCHED"
    NOT_EVALUATED = "NOT_EVALUATED"


class DiscrepancyType(StrEnum):
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    STATUS_MISMATCH = "STATUS_MISMATCH"
    MISSING_INTERNAL = "MISSING_INTERNAL"
    MISSING_EXTERNAL = "MISSING_EXTERNAL"
    WAITING_SOURCE = "WAITING_SOURCE"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    PROCESSING_ERROR = "PROCESSING_ERROR"


@dataclass(frozen=True, slots=True)
class SnapshotItem:
    observation_id: int
    observation: TransactionObservation


@dataclass(frozen=True, slots=True)
class RejectedRef:
    source: SourceKind
    payment_ref: str
    merchant_account: str
    currency: str


@dataclass(frozen=True, slots=True)
class RunInput:
    batch: ReconciliationBatch
    snapshot: tuple[SnapshotItem, ...]
    rejections: tuple[RejectedRef, ...]
    complete: Mapping[SourceKind, bool]
    now: datetime


@dataclass(frozen=True, slots=True)
class Outcome:
    payment_ref: str
    operation_type: OperationType
    match_status: MatchStatus
    rule: str
    discrepancy_types: tuple[DiscrepancyType, ...]
    left_ids: tuple[int, ...]
    right_ids: tuple[int, ...]
    amount_difference_minor: int | None
    score: float | None
    alternatives: tuple[int, ...]
    explanation: str


def snapshot_hash(items: Iterable[SnapshotItem]) -> str:
    rows = sorted((i.observation_id, i.observation.raw_hash) for i in items)
    return hashlib.sha256("".join(f"{a}:{b}\n" for a, b in rows).encode()).hexdigest()


def _ids(items: Iterable[SnapshotItem]) -> tuple[int, ...]:
    return tuple(sorted(i.observation_id for i in items))


def _weak_score(left: TransactionObservation, right: TransactionObservation) -> tuple[float, str]:
    score, reasons = 0.0, []
    if left.attempt_ref and left.attempt_ref == right.attempt_ref:
        score += WEAK_WEIGHTS["attempt_ref"]
        reasons.append("attempt_ref")
    if left.money == right.money:
        score += WEAK_WEIGHTS["amount"]
        reasons.append("amount")
    if abs(left.occurred_at.utc - right.occurred_at.utc) <= timedelta(hours=1):
        score += WEAK_WEIGHTS["time_1h"]
        reasons.append("time<=1h")
    return round(score, 4), "+".join(reasons) or "none"


def reconcile(inp: RunInput) -> list[Outcome]:
    batch = inp.batch
    left_src, right_src = batch.source_pair
    admitted = [i for i in inp.snapshot if batch.admits(i.observation)]
    groups: dict[tuple[str, OperationType], dict[SourceKind, list[SnapshotItem]]] = defaultdict(
        lambda: {left_src: [], right_src: []}
    )
    for item in admitted:
        obs = item.observation
        groups[(obs.payment_ref, obs.operation_type)][obs.source].append(item)
    rejected = {
        r.payment_ref
        for r in inp.rejections
        if r.merchant_account == batch.merchant_account and r.currency == batch.currency
    }

    outcomes: list[Outcome] = []
    left_single: list[SnapshotItem] = []
    right_single: list[SnapshotItem] = []

    def outcome(
        ref: str,
        op: OperationType,
        status: MatchStatus,
        rule: str,
        types: tuple[DiscrepancyType, ...],
        left: Iterable[SnapshotItem],
        right: Iterable[SnapshotItem],
        explanation: str,
        *,
        diff: int | None = None,
        score: float | None = None,
        alternatives: tuple[int, ...] = (),
    ) -> Outcome:
        return Outcome(
            ref,
            op,
            status,
            rule,
            types,
            _ids(left),
            _ids(right),
            diff,
            score,
            alternatives,
            explanation,
        )

    for (ref, op), sides in sorted(groups.items()):
        left, right = sides[left_src], sides[right_src]
        if len(left) > 1 or len(right) > 1:
            outcomes.append(
                outcome(
                    ref,
                    op,
                    MatchStatus.NOT_EVALUATED,
                    "duplicate_detection",
                    (DiscrepancyType.DUPLICATE_CANDIDATE,),
                    left,
                    right,
                    f"{len(left)} internal / {len(right)} external observations share the "
                    "reference; not forced into a match",
                )
            )
        elif ref in rejected:
            outcomes.append(
                outcome(
                    ref,
                    op,
                    MatchStatus.NOT_EVALUATED,
                    "processing_error",
                    (DiscrepancyType.PROCESSING_ERROR,),
                    left,
                    right,
                    "a row for this reference was quarantined at ingestion",
                )
            )
        elif left and right:
            a, b = left[0].observation, right[0].observation
            types: list[DiscrepancyType] = []
            diff = b.money.amount_minor - a.money.amount_minor
            if a.money != b.money:
                types.append(DiscrepancyType.AMOUNT_MISMATCH)
            if a.status != b.status:
                types.append(DiscrepancyType.STATUS_MISMATCH)
            if types:
                outcomes.append(
                    outcome(
                        ref,
                        op,
                        MatchStatus.UNMATCHED,
                        "strong_ref_linked",
                        tuple(types),
                        left,
                        right,
                        f"shared reference with differences: {', '.join(t.value for t in types)}",
                        diff=diff if a.money.currency == b.money.currency else None,
                    )
                )
            else:
                outcomes.append(
                    outcome(
                        ref,
                        op,
                        MatchStatus.EXACT,
                        "strong_ref_unique",
                        (),
                        left,
                        right,
                        "unique shared reference, identical money and status",
                        diff=0,
                    )
                )
        elif left:
            left_single.append(left[0])
        else:
            right_single.append(right[0])

    outcomes += _weak_phase(left_single, right_single, inp)
    return sorted(
        outcomes, key=lambda o: (o.payment_ref, o.operation_type, o.left_ids, o.right_ids)
    )


def _weak_phase(
    left_single: list[SnapshotItem], right_single: list[SnapshotItem], inp: RunInput
) -> list[Outcome]:
    left_src, right_src = inp.batch.source_pair
    scores: dict[tuple[int, int], tuple[float, str]] = {}
    for a in left_single:
        for b in right_single:
            if a.observation.operation_type != b.observation.operation_type:
                continue
            s = _weak_score(a.observation, b.observation)
            if s[0] >= WEAK_THRESHOLD:
                scores[(a.observation_id, b.observation_id)] = s

    def best(pairs: dict[int, list[tuple[float, int]]], key: int) -> tuple[int | None, bool]:
        ranked = sorted(pairs.get(key, []), reverse=True)
        if not ranked:
            return None, False
        tied = len(ranked) > 1 and ranked[0][0] == ranked[1][0]
        return ranked[0][1], tied

    by_left: dict[int, list[tuple[float, int]]] = defaultdict(list)
    by_right: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for (left_id, right_id), (value, _) in scores.items():
        by_left[left_id].append((value, right_id))
        by_right[right_id].append((value, left_id))

    outcomes: list[Outcome] = []
    paired: set[int] = set()
    items = {i.observation_id: i for i in left_single + right_single}
    for a in sorted(left_single, key=lambda i: i.observation_id):
        choice, tied = best(by_left, a.observation_id)
        if choice is None:
            continue
        back, back_tied = best(by_right, choice)
        alternatives = tuple(sorted(b for _, b in by_left[a.observation_id] if b != choice))
        obs = a.observation
        if tied or back_tied or back != a.observation_id:
            outcomes.append(
                Outcome(
                    obs.payment_ref,
                    obs.operation_type,
                    MatchStatus.UNMATCHED,
                    "weak_ambiguous",
                    (),
                    (a.observation_id,),
                    (),
                    None,
                    None,
                    tuple(sorted(b for _, b in by_left[a.observation_id])),
                    "several weak candidates with equal rank; ambiguity kept for review",
                )
            )
            paired.add(a.observation_id)
            continue
        score, reason = scores[(a.observation_id, choice)]
        other = items[choice].observation
        outcomes.append(
            Outcome(
                obs.payment_ref,
                obs.operation_type,
                MatchStatus.PROBABLE,
                "weak_rank",
                (),
                (a.observation_id,),
                (choice,),
                other.money.amount_minor - obs.money.amount_minor
                if other.money.currency == obs.money.currency
                else None,
                score,
                alternatives,
                f"ranking score {score} from {reason}; not a calibrated probability",
            )
        )
        paired.update({a.observation_id, choice})

    closed = inp.batch.is_closed(inp.now)
    for item in sorted(left_single + right_single, key=lambda i: i.observation_id):
        if item.observation_id in paired:
            continue
        obs = item.observation
        is_left = obs.source == left_src
        other_complete = inp.complete.get(right_src if is_left else left_src, False)
        if closed and other_complete:
            kind = DiscrepancyType.MISSING_EXTERNAL if is_left else DiscrepancyType.MISSING_INTERNAL
            why = "window closed and counterpart source complete"
        else:
            kind = DiscrepancyType.WAITING_SOURCE
            why = "counterpart may still arrive (window open or source incomplete)"
        ids = (item.observation_id,)
        outcomes.append(
            Outcome(
                obs.payment_ref,
                obs.operation_type,
                MatchStatus.UNMATCHED,
                "missing_side",
                (kind,),
                ids if is_left else (),
                () if is_left else ids,
                None,
                None,
                (),
                why,
            )
        )
    return outcomes
