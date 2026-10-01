"""Pure retrieval policy: query parsing, Reciprocal Rank Fusion and abstention.

Scores from different branches are never summed raw; only ranks are fused with RRF.
Abstention is explicit: a query that names an error code no authorized chunk contains,
or whose best result covers too little of the query, returns no evidence instead of a
weak guess.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from recon_knowledge.embedding import normalize

RRF_K = 60
BRANCH_K = 20
TOP_K = 5
# Tuned on the `dev` split only (see `recon_knowledge.evaluation`); holdout is reported.
ABSTAIN_COVERAGE = 0.6
_CODE = re.compile(r"\b[A-Z]\d{2}\b")
_TOKEN = re.compile(r"[a-z0-9_]+")
STOPWORDS = frozenset(
    """
    a al algo ante con como cual cuales cuando de del desde donde el ella en entre era es esa
    ese esta este esto fue han hay la las le les lo los mas me mi muy no o otra otro para pero
    por puede que se segun ser si sin sobre su sus tiene un una uno y ya debo cuanto cuanta
    que quien sigue
    the an and are as at be by can do does for from has have how in is it its of on or that
    this to was what when where which who why will with than
    """.split()
)


class Mode(StrEnum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class SearchContext:
    """Filters come from the authenticated context and structured fields, never the model."""

    tenant_id: str
    roles: tuple[str, ...]
    as_of: datetime
    provider_id: str | None = None


@dataclass(frozen=True, slots=True)
class Hit:
    chunk_id: str
    document_id: str
    version: int
    section_slug: str
    section_path: str
    title: str
    content: str
    content_hash: str
    start_line: int
    end_line: int
    effective_from: datetime
    rrf_score: float
    branches: tuple[str, ...]
    flagged_instructions: bool

    @property
    def evidence_unit(self) -> str:
        return f"{self.document_id}@{self.version}#{self.section_slug}"

    @property
    def citation(self) -> str:
        return f"[{self.document_id}@{self.version}#{self.chunk_id}]"

    @property
    def locator(self) -> str:
        return f"{self.section_slug}:L{self.start_line}-L{self.end_line}"


@dataclass(frozen=True, slots=True)
class SearchResult:
    mode: Mode
    hits: tuple[Hit, ...]
    abstained: bool
    reason: str | None
    warnings: tuple[str, ...] = field(default=())
    ranking: str = f"rrf(k={RRF_K})"


def query_codes(query: str) -> tuple[str, ...]:
    return tuple(sorted(set(_CODE.findall(query))))


def terms(text: str) -> set[str]:
    out = set()
    for token in _TOKEN.findall(normalize(text)):
        if len(token) < 3 or token in STOPWORDS:
            continue
        stem = token
        if len(token) > 4 and token.endswith("es"):
            stem = token[:-2]
        elif len(token) > 3 and token.endswith("s"):
            stem = token[:-1]
        out.add(stem)
    return out


def coverage(query: str, content: str) -> float:
    wanted = terms(query)
    if not wanted:
        return 0.0
    return len(wanted & terms(content)) / len(wanted)


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Fuse ranked ID lists: score = sum(1 / (k + rank)), rank starting at 1."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(dict.fromkeys(ranking), start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def abstention(query: str, hits: Sequence[Hit], threshold: float = ABSTAIN_COVERAGE) -> str | None:
    """Return a reason to abstain, or None when the evidence is sufficient."""
    if not hits:
        return "no authorized evidence matched the query"
    codes = query_codes(query)
    if codes and not any(code in _CODE.findall(h.content) for h in hits for code in codes):
        return "the requested error code is not documented in the authorized corpus"
    best = max(coverage(query, f"{h.title}\n{h.content}") for h in hits)
    if best < threshold:
        return f"best evidence covers {best:.2f} of the query terms (< {threshold})"
    return None
