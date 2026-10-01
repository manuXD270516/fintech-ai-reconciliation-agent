"""Retrieval evaluation (docs/07-evals.md): lexical-only, vector-only and hybrid baselines.

Relevance is judged on canonical evidence units (`document@version#section`) so that
overlapping chunks cannot inflate recall. The abstention threshold is tuned on the `dev`
split only and then reported on `holdout`. Authorization is checked by an independent
oracle built from corpus metadata, not by the SQL under test. Results are MEASURED on a
synthetic corpus with non-semantic hashing embeddings; they do not generalize.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from recon_knowledge.corpus import SourceDocument
from recon_knowledge.retrieval import ABSTAIN_COVERAGE, TOP_K, SearchContext, SearchResult

DEFAULT_AS_OF = "2026-10-01T00:00:00+00:00"
THRESHOLDS = tuple(round(0.1 * i, 1) for i in range(10))


@dataclass(frozen=True, slots=True)
class Query:
    query_id: str
    family: str
    split: str
    query: str
    relevant: tuple[str, ...]
    ctx: SearchContext
    case: str | None = None

    @property
    def answerable(self) -> bool:
        return bool(self.relevant)


def load_queries(path: Path, tenant_id: str = "tenant-demo") -> list[Query]:
    queries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw: dict[str, Any] = json.loads(line)
        queries.append(
            Query(
                query_id=raw["query_id"],
                family=raw["family"],
                split=raw["split"],
                query=raw["query"],
                relevant=tuple(raw["relevant"]),
                case=raw.get("case"),
                ctx=SearchContext(
                    tenant_id=raw.get("tenant_id", tenant_id),
                    roles=tuple(raw.get("roles", ["analyst"])),
                    as_of=datetime.fromisoformat(raw.get("as_of", DEFAULT_AS_OF)),
                    provider_id=raw.get("provider_id"),
                ),
            )
        )
    return queries


def check_splits(queries: Iterable[Query]) -> list[str]:
    """A family must live in exactly one split (no leakage between dev and holdout)."""
    seen: dict[str, set[str]] = {}
    for q in queries:
        seen.setdefault(q.family, set()).add(q.split)
    return [f for f, splits in sorted(seen.items()) if len(splits) > 1]


def authorized(doc: SourceDocument, ctx: SearchContext) -> bool:
    return (
        doc.review_status == "published"
        and doc.tenant_scope in ("global", ctx.tenant_id)
        and bool(set(doc.acl) & set(ctx.roles))
        and (ctx.provider_id is None or doc.provider_id in (None, ctx.provider_id))
        and doc.effective_from <= ctx.as_of
        and (doc.effective_to is None or doc.effective_to > ctx.as_of)
        and doc.published_at <= ctx.as_of
    )


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


@dataclass
class Scored:
    query: Query
    returned: list[str]
    abstained: bool
    seconds: float
    acl_violations: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        if not self.returned:
            return 0.0
        return len(set(self.returned) & set(self.query.relevant)) / len(self.returned)

    @property
    def recall(self) -> float:
        return len(set(self.returned) & set(self.query.relevant)) / len(self.query.relevant)

    @property
    def reciprocal_rank(self) -> float:
        for rank, unit in enumerate(self.returned, start=1):
            if unit in self.query.relevant:
                return 1.0 / rank
        return 0.0


def score(
    query: Query, result: SearchResult, seconds: float, corpus: dict[str, SourceDocument]
) -> Scored:
    units = list(dict.fromkeys(h.evidence_unit for h in result.hits))[:TOP_K]
    # A document outside the evaluated corpus is a violation too (unknown provenance).
    violations = [
        h.chunk_id
        for h in result.hits
        if (doc := corpus.get(f"{h.document_id}@{h.version}")) is None
        or not authorized(doc, query.ctx)
    ]
    return Scored(query, units, result.abstained or not units, seconds, violations)


def summarize(rows: list[Scored]) -> dict[str, Any]:
    answerable = [r for r in rows if r.query.answerable]
    unanswerable = [r for r in rows if not r.query.answerable]
    correct_abstentions = sum(r.abstained for r in unanswerable)
    hit_any = sum(r.recall > 0 for r in answerable)
    latencies = sorted(r.seconds for r in rows)

    def mean(values: list[float]) -> float | None:
        return round(statistics.fmean(values), 4) if values else None

    return {
        "n_queries": len(rows),
        "n_answerable": len(answerable),
        "n_unanswerable": len(unanswerable),
        "precision_at_5_macro": mean([r.precision for r in answerable]),
        "recall_at_5_macro": mean([r.recall for r in answerable]),
        "mrr": mean([r.reciprocal_rank for r in answerable]),
        "answerable_hit_rate": round(hit_any / len(answerable), 4) if answerable else None,
        "answerable_hit_rate_ci95": wilson(hit_any, len(answerable)),
        "false_abstentions": sum(r.abstained for r in answerable),
        "no_answer_abstention": (
            round(correct_abstentions / len(unanswerable), 4) if unanswerable else None
        ),
        "no_answer_abstention_ci95": wilson(correct_abstentions, len(unanswerable)),
        "acl_violations": sum(len(r.acl_violations) for r in rows),
        "latency_p50_ms": round(1000 * latencies[len(latencies) // 2], 2) if rows else None,
        "latency_p95_ms": (
            round(
                1000 * latencies[min(len(latencies) - 1, math.ceil(0.95 * len(latencies)) - 1)], 2
            )
            if rows
            else None
        ),
    }


def objective(summary: dict[str, Any]) -> float:
    """Balance coverage and abstention so 'always abstain' cannot win."""
    recall = summary["recall_at_5_macro"] or 0.0
    abstain = summary["no_answer_abstention"] or 0.0
    return round((recall + abstain) / 2, 6)


def tune(dev_rows_by_threshold: dict[float, list[Scored]]) -> float:
    """Pick the abstention threshold with the best dev objective (ties: lowest)."""
    return max(
        sorted(dev_rows_by_threshold),
        key=lambda t: (objective(summarize(dev_rows_by_threshold[t])), -t),
    )


def failures(rows: list[Scored]) -> list[dict[str, Any]]:
    return [
        {
            "query_id": r.query.query_id,
            "case": r.query.case,
            "expected": list(r.query.relevant),
            "returned": r.returned,
            "abstained": r.abstained,
        }
        for r in rows
        if (r.query.answerable and r.recall < 1) or (not r.query.answerable and not r.abstained)
    ]


def configured_threshold() -> float:
    return ABSTAIN_COVERAGE
