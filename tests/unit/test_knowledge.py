"""M3 T01-T03: corpus contract, chunking, local embeddings and retrieval policy (no DB)."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from recon_knowledge.chunking import MAX_TOKENS, OVERLAP_TOKENS, chunk_document
from recon_knowledge.corpus import (
    CorpusError,
    SourceDocument,
    corpus_manifest,
    load_corpus,
    parse_document,
)
from recon_knowledge.embedding import DIMENSIONS, HashingEmbedder, cosine
from recon_knowledge.evaluation import authorized, check_splits, load_queries, wilson
from recon_knowledge.retrieval import (
    Hit,
    SearchContext,
    abstention,
    coverage,
    query_codes,
    rrf,
)

CORPUS = Path(__file__).resolve().parents[2] / "datasets" / "synthetic" / "knowledge-v1"
HEADER = """---
document_id: t-doc
version: 1
tenant_scope: global
acl: analyst
document_type: runbook
title: Test
language: es
effective_from: 2026-01-01T00:00:00+00:00
published_at: 2026-01-01T00:00:00+00:00
review_status: published
---
"""


def _docs() -> dict[str, SourceDocument]:
    return {d.key: d for d in load_corpus(CORPUS)}


def test_corpus_is_valid_versioned_and_manifested() -> None:
    docs = _docs()
    assert len(docs) == 17
    assert {d.review_status for d in docs.values()} == {"published", "draft", "revoked"}
    assert "alfa-error-codes@1" in docs and "alfa-error-codes@2" in docs
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == corpus_manifest(CORPUS)
    assert manifest["data_origin"] == "SYNTHETIC"


def test_queries_point_to_existing_evidence_units_without_split_leakage() -> None:
    units = {c.evidence_unit for d in _docs().values() for c in chunk_document(d)}
    queries = load_queries(CORPUS / "queries.jsonl")
    assert len(queries) == 38
    assert check_splits(queries) == []
    for q in queries:
        assert set(q.relevant) <= units, q.query_id
    assert {q.split for q in queries} == {"dev", "holdout"}
    assert sum(not q.answerable for q in queries) == 8


def _pan() -> str:
    base = "400000000000000"
    for check in "0123456789":
        digits = base + check
        total = 0
        for i, ch in enumerate(reversed(digits)):
            n = int(ch) * (2 if i % 2 else 1)
            total += n - 9 if n > 9 else n
        if total % 10 == 0:
            return digits
    raise AssertionError("unreachable")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("acl: analyst", "acl: root"), "acl"),
        (("review_status: published", "review_status: live"), "review_status"),
        (("language: es", "language: fr"), "language"),
        (("document_type: runbook", "document_type: memo"), "document_type"),
        (("title: Test\n", ""), "missing metadata"),
        (
            ("published_at:", "effective_to: 2025-01-01T00:00:00+00:00\npublished_at:"),
            "effective_to",
        ),
    ],
)
def test_invalid_metadata_is_rejected(mutation: tuple[str, str], message: str) -> None:
    text = (HEADER + "# T\n\n## A\nbody\n").replace(*mutation)
    with pytest.raises(CorpusError, match=message):
        parse_document(text)


def test_card_like_numbers_and_keys_are_rejected() -> None:
    with pytest.raises(CorpusError, match="card-like"):
        parse_document(HEADER + f"# T\n\n## A\ncard {_pan()}\n")
    with pytest.raises(CorpusError, match="key material"):
        marker = "-----BEGIN RSA " + "PRIVATE KEY-----"  # split so the repo scan stays clean
        parse_document(HEADER + f"# T\n\n## A\n{marker}\n")


def test_chunks_follow_sections_codes_and_flags() -> None:
    docs = _docs()
    chunks = chunk_document(docs["alfa-error-codes@2"])
    slugs = [c.section_slug for c in chunks]
    assert slugs[0] == "intro"
    assert "e17-captura-duplicada-detectada" in slugs
    e17 = next(c for c in chunks if c.section_slug.startswith("e17"))
    assert e17.error_codes == ("E17",)
    assert e17.content.startswith("E17")
    assert chunk_document(docs["alfa-error-codes@2"]) == chunks  # deterministic IDs
    faq = {c.section_slug: c for c in chunk_document(docs["alfa-status-faq@1"])}
    assert faq["nota-del-portal"].flagged_instructions
    assert not faq["estado-pending"].flagged_instructions
    lines = docs["alfa-error-codes@2"].body.splitlines()
    assert e17.start_line < e17.end_line <= docs["alfa-error-codes@2"].body_start_line + len(lines)


def test_long_sections_split_with_overlap_and_keep_lists() -> None:
    paragraph = " ".join(f"palabra{i}" for i in range(300))
    steps = "\n".join(f"{i}. paso numerado {i}" for i in range(1, 6))
    body = f"# T\n\n## Larga\n{paragraph}\n\n{steps}\n\n{paragraph}\n\n{paragraph}\n"
    chunks = chunk_document(parse_document(HEADER + body))
    assert len(chunks) > 1
    assert all(c.token_count <= MAX_TOKENS + OVERLAP_TOKENS + 10 for c in chunks)
    assert sum(steps in c.content for c in chunks) >= 1
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert {c.evidence_unit for c in chunks} == {"t-doc@1#larga"}


def test_hashing_embeddings_are_deterministic_normalized_and_lexical() -> None:
    emb = HashingEmbedder()
    a = emb.embed("liquidación neta de comisión")
    assert emb.embed("liquidación neta de comisión") == a
    assert len(a) == DIMENSIONS
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, abs_tol=1e-4)
    near = cosine(a, emb.embed("liquidacion neta comision descontada"))
    far = cosine(a, emb.embed("política de vacaciones del equipo"))
    assert near > far
    assert emb.manifest["semantic"] is False
    assert emb.embed("¿?") == [0.0] * DIMENSIONS


def test_rrf_fuses_ranks_not_scores() -> None:
    fused = rrf([["a", "b", "c"], ["b", "a"], ["c"]])
    assert fused[0][0] in {"a", "b"}
    assert math.isclose(dict(fused)["a"], 1 / 61 + 1 / 62)
    assert math.isclose(dict(fused)["c"], 1 / 63 + 1 / 61)
    assert rrf([["x", "x", "y"]]) == [("x", 1 / 61), ("y", 1 / 62)]
    assert [k for k, _ in rrf([["b"], ["a"]])] == ["a", "b"]  # ties broken by id


def _hit(content: str) -> Hit:
    return Hit("c1", "d", 1, "s", "p", "Título", content, "h", 1, 2,
               datetime(2026, 1, 1, tzinfo=UTC), 0.1, ("lexical",), False)  # fmt: skip


def test_abstention_rules() -> None:
    assert query_codes("error E17 y B19") == ("B19", "E17")
    assert abstention("algo", []) is not None
    assert "error code" in str(abstention("Código Z99 de prov-beta", [_hit("E17 captura")]))
    assert abstention("captura duplicada rechazada", [_hit("captura duplicada rechazada")]) is None
    assert abstention("tasa de cambio EUR JPY gamma", [_hit("captura duplicada")]) is not None
    assert coverage("comisiones netas", "comisión neta") == 1.0


def test_authorization_oracle_and_wilson() -> None:
    docs = _docs()
    now = datetime(2026, 10, 1, tzinfo=UTC)
    analyst = SearchContext("tenant-demo", ("analyst",), now)
    assert authorized(docs["alfa-error-codes@2"], analyst)
    assert not authorized(docs["alfa-error-codes@1"], analyst)  # superseded window
    assert not authorized(docs["other-tenant-runbook@1"], analyst)
    assert not authorized(docs["procedure-fee-waivers@1"], analyst)
    assert authorized(
        docs["procedure-fee-waivers@1"], SearchContext("tenant-demo", ("supervisor",), now)
    )
    assert not authorized(docs["beta-fee-draft@1"], analyst)
    assert not authorized(docs["alfa-promo-fees@1"], analyst)
    early = SearchContext("tenant-demo", ("analyst",), datetime(2026, 8, 10, tzinfo=UTC))
    assert not authorized(docs["incident-inc-0815@1"], early)
    assert wilson(0, 0) is None
    low, high = wilson(8, 8) or (0.0, 0.0)
    assert high == 1.0 and 0.6 < low < 0.7
