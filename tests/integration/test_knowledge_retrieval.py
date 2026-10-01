"""M3 T04-T06: publication, hard filters and hybrid retrieval on real PostgreSQL + pgvector."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import func, select

from recon_knowledge.corpus import load_corpus, parse_document
from recon_knowledge.repository import KnowledgeConflictError, KnowledgeRepository
from recon_knowledge.retrieval import Mode, SearchContext
from recon_store.engine import runtime_engine, runtime_url
from recon_store.tables import knowledge_chunks, knowledge_documents

from .support import app_connect, new_run_id, settings

pytestmark = pytest.mark.integration
CORPUS = Path(__file__).resolve().parents[2] / "datasets" / "synthetic" / "knowledge-v1"
NOW = datetime(2026, 10, 1, tzinfo=UTC)
ANALYST = SearchContext("tenant-demo", ("analyst",), NOW)


@pytest.fixture(scope="module")
def repo() -> Iterator[KnowledgeRepository]:
    s = settings()
    engine = runtime_engine(
        runtime_url(s.db_host, s.db_port, s.db_name, s.db_user, s.db_password.get_secret_value())
    )
    repository = KnowledgeRepository(engine)
    for doc in load_corpus(CORPUS):
        repository.publish(doc, actor="svc-it", correlation_id="it")
    yield repository
    engine.dispose()


def _units(repo: KnowledgeRepository, query: str, ctx: SearchContext, mode: Mode) -> list[str]:
    return [h.evidence_unit for h in repo.search(query, ctx, mode).hits]


def _scoped(doc_id: str) -> SearchContext:
    """Test documents live in their own tenant so they never leak into other suites."""
    return SearchContext(doc_id, ("analyst",), NOW)


def _doc(doc_id: str, body: str, version: int = 1) -> str:
    return f"""---
document_id: {doc_id}
version: {version}
tenant_scope: {doc_id}
acl: analyst
document_type: runbook
title: Prueba de integración {doc_id}
language: es
effective_from: 2026-01-01T00:00:00+00:00
published_at: 2026-01-01T00:00:00+00:00
review_status: published
---
# Prueba {doc_id}

## Sección única
{body}
"""


def test_publication_is_idempotent_and_versions_are_immutable(repo: KnowledgeRepository) -> None:
    docs = load_corpus(CORPUS)
    assert {repo.publish(d, actor="svc-it", correlation_id="it") for d in docs} == {"unchanged"}
    tampered = replace(docs[0], body=docs[0].body + "\nalterado\n")
    with pytest.raises(KnowledgeConflictError):
        repo.publish(tampered, actor="svc-it", correlation_id="it")


def test_failed_embedding_leaves_previous_version_active(repo: KnowledgeRepository) -> None:
    doc_id = f"it-atomic-{new_run_id()}"
    marker = doc_id.replace("-", "")
    v1 = parse_document(_doc(doc_id, f"texto estable zircónico versión uno {marker}"))
    repo.publish(v1, actor="svc-it", correlation_id="it")
    calls = {"n": 0}

    def flaky(text: str) -> list[float]:
        calls["n"] += 1
        raise RuntimeError("embedding provider unavailable")

    broken = KnowledgeRepository(repo.engine, embed=flaky)
    v2 = parse_document(_doc(doc_id, "texto nuevo zircónico versión dos", version=2))
    with pytest.raises(RuntimeError):
        broken.publish(v2, actor="svc-it", correlation_id="it")
    assert calls["n"] == 1
    with repo.engine.connect() as conn:
        versions = conn.execute(
            select(knowledge_documents.c.version).where(knowledge_documents.c.document_id == doc_id)
        ).all()
    assert [v[0] for v in versions] == [1]
    units = _units(repo, f"texto zircónico versión uno {marker}", _scoped(doc_id), Mode.HYBRID)
    assert not any(u.startswith(doc_id) for u in _units(repo, marker, ANALYST, Mode.HYBRID))
    assert units[0] == f"{doc_id}@1#seccion-unica"
    assert not any(u.startswith(f"{doc_id}@2") for u in units)


def test_rg01_error_code_lookup_returns_current_document(repo: KnowledgeRepository) -> None:
    ctx = replace(ANALYST, provider_id="prov-alfa")
    units = _units(repo, "¿Qué significa el error E17 de prov-alfa?", ctx, Mode.HYBRID)
    assert units[0] == "alfa-error-codes@2#e17-captura-duplicada-detectada"
    assert not any(u.startswith("alfa-error-codes@1") for u in units)


def test_rg02_as_of_selects_the_applicable_version(repo: KnowledgeRepository) -> None:
    past = replace(ANALYST, as_of=datetime(2026, 3, 1, tzinfo=UTC), provider_id="prov-alfa")
    units = _units(repo, "código E17 de prov-alfa", past, Mode.HYBRID)
    assert units[0] == "alfa-error-codes@1#e17-captura-pendiente-de-confirmacion"
    assert not any(u.startswith("alfa-error-codes@2") for u in units)
    early = replace(ANALYST, as_of=datetime(2026, 8, 10, tzinfo=UTC))
    for mode in Mode:
        assert not any(
            u.startswith("incident-inc-0815")
            for u in _units(repo, "liquidación neta inesperada prov-alfa", early, mode)
        )


def test_rg03_abstains_without_evidence(repo: KnowledgeRepository) -> None:
    for query in ("Código de error Z99 de prov-beta", "tasa de cambio EUR a JPY de prov-gamma"):
        result = repo.search(query, ANALYST, Mode.HYBRID)
        assert result.abstained and result.hits == () and result.reason


def test_rg04_other_tenant_content_is_never_exposed(repo: KnowledgeRepository) -> None:
    for mode in Mode:
        for query in ("acuerdo especial ZETA-77 contrato marco", "E17 captura duplicada"):
            hits = repo.search(query, ANALYST, mode).hits
            assert not any(h.document_id == "other-tenant-runbook" for h in hits)
    other = SearchContext("tenant-other", ("analyst",), NOW)
    assert "other-tenant-runbook@1#acuerdo-especial-e17" in _units(
        repo, "acuerdo especial ZETA-77", other, Mode.HYBRID
    )
    assert repo.search("ZETA-77", ANALYST, Mode.LEXICAL).hits == ()
    foreign = repo.search("ZETA-77", other, Mode.LEXICAL).hits[0].chunk_id
    assert repo.get_chunk(foreign, ANALYST) is None


def test_acl_draft_and_revoked_are_hard_filters(repo: KnowledgeRepository) -> None:
    query = "umbral de condonación de comisiones"
    supervisor = replace(ANALYST, roles=("supervisor",))
    assert "procedure-fee-waivers@1#umbral-de-condonacion" in _units(
        repo, query, supervisor, Mode.HYBRID
    )
    for mode in Mode:
        assert not any(
            u.startswith("procedure-fee-waivers") for u in _units(repo, query, ANALYST, mode)
        )
        for q in ("nueva comisión de 2.75 de prov-beta", "promoción sin comisión prov-alfa"):
            assert not any(
                u.startswith(("beta-fee-draft", "alfa-promo-fees"))
                for u in _units(repo, q, ANALYST, mode)
            )


def test_revocation_removes_from_every_branch(repo: KnowledgeRepository) -> None:
    run = new_run_id()
    doc_id = f"it-revoke-{run}"
    query = f"procedimiento wolframio Q42 lote{run}"
    repo.publish(parse_document(_doc(doc_id, query)), actor="it", correlation_id="it")
    ctx = _scoped(doc_id)
    assert _units(repo, query, ctx, Mode.HYBRID)[0].startswith(doc_id)
    chunk_id = repo.search(query, ctx, Mode.HYBRID).hits[0].chunk_id
    assert repo.revoke(doc_id, 1, actor="curator-it", correlation_id="it", reason="obsoleto")
    for mode in Mode:
        assert not any(u.startswith(doc_id) for u in _units(repo, query, ctx, mode))
    assert repo.get_chunk(chunk_id, ctx) is None
    assert not repo.revoke(doc_id, 1, actor="curator-it", correlation_id="it", reason="again")


def test_untrusted_instructions_are_returned_as_flagged_data(repo: KnowledgeRepository) -> None:
    ctx = replace(ANALYST, provider_id="prov-alfa")
    result = repo.search("nota del portal de prov-alfa sobre estados", ctx, Mode.HYBRID)
    flagged = [h for h in result.hits if h.flagged_instructions]
    assert flagged and all(
        f"untrusted_instructions:{h.chunk_id}" in result.warnings for h in flagged
    )


def test_index_stores_versioned_embedding_metadata(repo: KnowledgeRepository) -> None:
    with repo.engine.connect() as conn:
        rows = conn.execute(
            select(
                knowledge_chunks.c.embedding_model,
                knowledge_chunks.c.embedding_revision,
                knowledge_chunks.c.dimensions,
                func.count(),
            ).group_by(
                knowledge_chunks.c.embedding_model,
                knowledge_chunks.c.embedding_revision,
                knowledge_chunks.c.dimensions,
            )
        ).all()
    assert [(r[0], r[1], r[2]) for r in rows] == [("hashing-ngram", "v1", 256)]


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM recon.knowledge_documents WHERE false",
        "UPDATE recon.knowledge_documents SET acl = '{}' WHERE false",
        "UPDATE recon.knowledge_chunks SET content = '' WHERE false",
        "DELETE FROM recon.knowledge_chunks WHERE false",
    ],
)
def test_runtime_role_cannot_rewrite_knowledge(statement: str) -> None:
    with app_connect() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)
