"""PostgreSQL knowledge repository: atomic version publication and hybrid retrieval.

Every retrieval branch applies the same hard filters (published, tenant scope, ACL,
provider, validity window and publication date relative to `as_of`). Nothing outside
that universe is used as a fallback to fill top-k.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, cast, func, insert, literal, select, text, update
from sqlalchemy.dialects.postgresql import REGCONFIG

from recon_knowledge.chunking import CHUNKING_VERSION, chunk_document
from recon_knowledge.corpus import SourceDocument
from recon_knowledge.embedding import HashingEmbedder
from recon_knowledge.retrieval import (
    ABSTAIN_COVERAGE,
    BRANCH_K,
    TOP_K,
    Hit,
    Mode,
    SearchContext,
    SearchResult,
    abstention,
    query_codes,
    rrf,
)
from recon_store.tables import audit_entries, knowledge_chunks, knowledge_documents
from recon_store.vector import to_literal

INDEX_VERSION = f"{CHUNKING_VERSION}+hashing-ngram/v1"


class KnowledgeConflictError(Exception):
    """A document version already exists with different content (versions are immutable)."""


_AUTHORIZED = """
    d.review_status = 'published'
    AND d.tenant_scope IN ('global', :tenant)
    AND d.acl && CAST(:roles AS varchar[])
    AND (CAST(:provider AS varchar) IS NULL OR d.provider_id IS NULL OR d.provider_id = :provider)
    AND d.effective_from <= :as_of
    AND (d.effective_to IS NULL OR d.effective_to > :as_of)
    AND d.published_at <= :as_of
"""
_FROM = "recon.knowledge_chunks c JOIN recon.knowledge_documents d ON d.id = c.document_pk"

_LEXICAL = text(f"""
WITH q AS (
  SELECT
    to_tsquery('spanish', coalesce((SELECT string_agg(quote_literal(lexeme), ' | ')
                                    FROM unnest(to_tsvector('spanish', :q))), '')) AS es,
    to_tsquery('english', coalesce((SELECT string_agg(quote_literal(lexeme), ' | ')
                                    FROM unnest(to_tsvector('english', :q))), '')) AS en
)
SELECT c.chunk_id,
       ts_rank_cd(c.tsv, CASE WHEN c.fts_config = 'english' THEN q.en ELSE q.es END) AS rank
FROM {_FROM}, q
WHERE {_AUTHORIZED}
  AND c.tsv @@ (CASE WHEN c.fts_config = 'english' THEN q.en ELSE q.es END)
ORDER BY rank DESC, c.chunk_id
LIMIT :k
""")  # noqa: S608 - static fragments; all values are bound parameters

_CODES = text(f"""
SELECT c.chunk_id
FROM {_FROM}
WHERE {_AUTHORIZED} AND c.error_codes && CAST(:codes AS varchar[])
ORDER BY cardinality(ARRAY(SELECT unnest(c.error_codes) INTERSECT
                           SELECT unnest(CAST(:codes AS varchar[])))) DESC,
         cardinality(c.error_codes), c.chunk_id
LIMIT :k
""")  # noqa: S608

_VECTOR = text(f"""
SELECT c.chunk_id, 1 - (c.embedding <=> CAST(:qv AS vector)) AS similarity
FROM {_FROM}
WHERE {_AUTHORIZED}
ORDER BY c.embedding <=> CAST(:qv AS vector), c.chunk_id
LIMIT :k
""")  # noqa: S608

_DETAILS = text(f"""
SELECT c.chunk_id, d.document_id, d.version, c.section_slug, c.section_path, d.title,
       c.content, c.content_hash, c.start_line, c.end_line, d.effective_from,
       c.flagged_instructions
FROM {_FROM}
WHERE {_AUTHORIZED} AND c.chunk_id = ANY(CAST(:ids AS varchar[]))
""")  # noqa: S608


@dataclass(frozen=True, slots=True)
class Timed:
    result: SearchResult
    seconds: float


class KnowledgeRepository:
    def __init__(
        self,
        engine: Engine,
        embedder: HashingEmbedder | None = None,
        embed: Callable[[str], list[float]] | None = None,
    ) -> None:
        self.engine = engine
        self.embedder = embedder or HashingEmbedder()
        self._embed = embed or self.embedder.embed

    # --- publication ----------------------------------------------------------------

    def publish(self, doc: SourceDocument, *, actor: str, correlation_id: str) -> str:
        """Stage chunks + embeddings and make the version visible in one transaction.

        A failure anywhere (e.g. embeddings) rolls back the whole version, so a partially
        indexed document is never visible and the previous version stays active.
        """
        chunks = chunk_document(doc)
        with self.engine.begin() as conn:
            conn.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(doc.document_id, 0)))
            )
            existing = conn.execute(
                select(knowledge_documents.c.content_hash).where(
                    knowledge_documents.c.document_id == doc.document_id,
                    knowledge_documents.c.version == doc.version,
                )
            ).scalar_one_or_none()
            if existing is not None:
                if existing != doc.content_hash:
                    raise KnowledgeConflictError(doc.key)
                return "unchanged"
            doc_pk: int = conn.execute(
                insert(knowledge_documents)
                .values(
                    document_id=doc.document_id,
                    version=doc.version,
                    tenant_scope=doc.tenant_scope,
                    acl=list(doc.acl),
                    provider_id=doc.provider_id,
                    document_type=doc.document_type,
                    title=doc.title,
                    language=doc.language,
                    source_uri=doc.source_uri,
                    content_hash=doc.content_hash,
                    effective_from=doc.effective_from,
                    effective_to=doc.effective_to,
                    published_at=doc.published_at,
                    review_status=doc.review_status,
                    synthetic=True,
                    supersedes=doc.supersedes,
                    index_version=INDEX_VERSION,
                )
                .returning(knowledge_documents.c.id)
            ).scalar_one()
            for chunk in chunks:
                indexed = f"{doc.title}\n{chunk.content}"
                conn.execute(
                    insert(knowledge_chunks).values(
                        document_pk=doc_pk,
                        chunk_id=chunk.chunk_id,
                        section_slug=chunk.section_slug,
                        section_path=chunk.section_path,
                        ordinal=chunk.ordinal,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        token_count=chunk.token_count,
                        error_codes=list(chunk.error_codes),
                        flagged_instructions=chunk.flagged_instructions,
                        content=chunk.content,
                        content_hash=chunk.content_hash,
                        fts_config=doc.fts_config,
                        tsv=func.to_tsvector(cast(literal(doc.fts_config), REGCONFIG), indexed),
                        embedding=to_literal(self._embed(indexed)),
                        embedding_model=self.embedder.model,
                        embedding_revision=self.embedder.revision,
                        dimensions=self.embedder.dimensions,
                    )
                )
            self._audit(
                conn,
                actor,
                "knowledge.publish",
                doc.key,
                doc.version,
                correlation_id,
                {"chunks": len(chunks), "review_status": doc.review_status},
            )
        return "published"

    def revoke(
        self, document_id: str, version: int, *, actor: str, correlation_id: str, reason: str
    ) -> bool:
        """Revocation removes the version from every retrieval branch immediately."""
        with self.engine.begin() as conn:
            changed = conn.execute(
                update(knowledge_documents)
                .where(
                    knowledge_documents.c.document_id == document_id,
                    knowledge_documents.c.version == version,
                    knowledge_documents.c.review_status != "revoked",
                )
                .values(review_status="revoked")
            ).rowcount
            if changed:
                self._audit(
                    conn,
                    actor,
                    "knowledge.revoke",
                    f"{document_id}@{version}",
                    version,
                    correlation_id,
                    {"reason": reason[:200]},
                )
        return bool(changed)

    @staticmethod
    def _audit(
        conn: Connection,
        actor: str,
        action: str,
        resource_id: str,
        version: int,
        correlation_id: str,
        details: dict[str, Any],
    ) -> None:
        conn.execute(
            insert(audit_entries).values(
                tenant_id="global",
                actor=actor,
                action=action,
                resource_type="knowledge_document",
                resource_id=resource_id,
                resource_version=version,
                outcome="ok",
                correlation_id=correlation_id,
                details=details,
            )
        )

    # --- retrieval ------------------------------------------------------------------

    @staticmethod
    def _params(ctx: SearchContext) -> dict[str, Any]:
        return {
            "tenant": ctx.tenant_id,
            "roles": list(ctx.roles),
            "provider": ctx.provider_id,
            "as_of": ctx.as_of,
        }

    def search(
        self,
        query: str,
        ctx: SearchContext,
        mode: Mode = Mode.HYBRID,
        *,
        top_k: int = TOP_K,
        threshold: float = ABSTAIN_COVERAGE,
    ) -> SearchResult:
        params = self._params(ctx)
        rankings: list[tuple[str, list[str]]] = []
        with self.engine.connect() as conn:
            if mode in (Mode.LEXICAL, Mode.HYBRID):
                rows = conn.execute(_LEXICAL, params | {"q": query, "k": BRANCH_K}).all()
                rankings.append(("lexical", [r[0] for r in rows]))
            codes = query_codes(query)
            if mode is Mode.HYBRID and codes:
                rows = conn.execute(_CODES, params | {"codes": list(codes), "k": BRANCH_K}).all()
                rankings.append(("code", [r[0] for r in rows]))
            if mode in (Mode.VECTOR, Mode.HYBRID):
                vector = self.embedder.embed(query)
                if any(vector):
                    rows = conn.execute(
                        _VECTOR, params | {"qv": to_literal(vector), "k": BRANCH_K}
                    ).all()
                    rankings.append(("vector", [r[0] for r in rows]))
            fused = rrf([ids for _, ids in rankings])[:top_k]
            details = {
                r.chunk_id: r
                for r in conn.execute(
                    _DETAILS, params | {"ids": [chunk_id for chunk_id, _ in fused]}
                )
            }
        hits = tuple(
            Hit(
                chunk_id=chunk_id,
                document_id=details[chunk_id].document_id,
                version=details[chunk_id].version,
                section_slug=details[chunk_id].section_slug,
                section_path=details[chunk_id].section_path,
                title=details[chunk_id].title,
                content=details[chunk_id].content,
                content_hash=details[chunk_id].content_hash,
                start_line=details[chunk_id].start_line,
                end_line=details[chunk_id].end_line,
                effective_from=details[chunk_id].effective_from,
                rrf_score=round(score, 6),
                branches=tuple(name for name, ids in rankings if chunk_id in ids),
                flagged_instructions=details[chunk_id].flagged_instructions,
            )
            for chunk_id, score in fused
            if chunk_id in details
        )
        reason = abstention(query, hits, threshold)
        warnings = tuple(
            f"untrusted_instructions:{h.chunk_id}" for h in hits if h.flagged_instructions
        )
        if reason is not None:
            return SearchResult(mode, (), True, reason)
        return SearchResult(mode, hits, False, None, warnings)

    def timed_search(self, query: str, ctx: SearchContext, mode: Mode, **kw: Any) -> Timed:
        started = time.perf_counter()
        result = self.search(query, ctx, mode, **kw)
        return Timed(result, time.perf_counter() - started)

    def get_chunk(self, chunk_id: str, ctx: SearchContext) -> Hit | None:
        """Resolve a citation inside the caller's authorized universe (None otherwise)."""
        with self.engine.connect() as conn:
            row = conn.execute(_DETAILS, self._params(ctx) | {"ids": [chunk_id]}).first()
        if row is None:
            return None
        return Hit(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            version=row.version,
            section_slug=row.section_slug,
            section_path=row.section_path,
            title=row.title,
            content=row.content,
            content_hash=row.content_hash,
            start_line=row.start_line,
            end_line=row.end_line,
            effective_from=row.effective_from,
            rrf_score=0.0,
            branches=(),
            flagged_instructions=row.flagged_instructions,
        )
