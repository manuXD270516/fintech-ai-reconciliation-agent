"""Knowledge jobs.

    python -m recon_knowledge ingest   --corpus datasets/synthetic/knowledge-v1
    python -m recon_knowledge evaluate --corpus datasets/synthetic/knowledge-v1
    python -m recon_knowledge revoke   --document-id DOC --version N --actor ops --reason "..."

Both use the restricted runtime role from APP_DB_* (Compose `knowledge-ingest` job and the
smoke container). `evaluate` prints a JSON report (MEASURED, synthetic corpus).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, insert, update

from recon_knowledge.corpus import CorpusError, load_corpus
from recon_knowledge.embedding import HashingEmbedder
from recon_knowledge.evaluation import (
    THRESHOLDS,
    check_splits,
    configured_threshold,
    failures,
    load_queries,
    objective,
    score,
    summarize,
    tune,
)
from recon_knowledge.provider_status import StatusError, publish_snapshots
from recon_knowledge.repository import INDEX_VERSION, KnowledgeRepository
from recon_knowledge.retrieval import BRANCH_K, RRF_K, TOP_K, Mode
from recon_store.engine import runtime_engine, runtime_url
from recon_store.tables import audit_entries, knowledge_documents


def _engine() -> Engine:
    env = os.environ
    return runtime_engine(
        runtime_url(
            env["APP_DB_HOST"],
            int(env.get("APP_DB_PORT", "5432")),
            env["APP_DB_NAME"],
            env["APP_DB_USER"],
            env["APP_DB_PASSWORD"],
        )
    )


def ingest(corpus_dir: Path, status_file: Path | None = None) -> dict[str, Any]:
    docs = load_corpus(corpus_dir)
    engine = _engine()
    try:
        repo = KnowledgeRepository(engine)
        outcomes = {
            d.key: repo.publish(d, actor="svc-knowledge-ingest", correlation_id="knowledge-ingest")
            for d in docs
        }
        status = publish_snapshots(engine, status_file) if status_file else None
    finally:
        engine.dispose()
    result: dict[str, Any] = {
        "documents": len(docs),
        "published": sum(o == "published" for o in outcomes.values()),
        "unchanged": sum(o == "unchanged" for o in outcomes.values()),
        "index_version": INDEX_VERSION,
    }
    if status is not None:
        result["provider_status"] = status
    return result


def evaluate(corpus_dir: Path) -> dict[str, Any]:
    docs = {d.key: d for d in load_corpus(corpus_dir)}
    queries = load_queries(corpus_dir / "queries.jsonl")
    leaks = check_splits(queries)
    engine = _engine()
    try:
        repo = KnowledgeRepository(engine)
        runs: dict[tuple[Mode, float], list[Any]] = {}
        for mode in Mode:
            for threshold in THRESHOLDS:
                runs[(mode, threshold)] = [
                    score(q, t.result, t.seconds, docs)
                    for q in queries
                    for t in [repo.timed_search(q.query, q.ctx, mode, threshold=threshold)]
                ]
    finally:
        engine.dispose()

    def split(rows: list[Any], name: str) -> list[Any]:
        return [r for r in rows if r.query.split == name]

    tuned = {
        mode.value: tune({t: split(runs[(mode, t)], "dev") for t in THRESHOLDS}) for mode in Mode
    }
    configured = configured_threshold()
    report: dict[str, Any] = {
        "kind": "MEASURED",
        "scope": "synthetic corpus knowledge-v1; hashing embeddings are not semantic",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": os.environ.get("RECON_COMMIT", "see enclosing smoke report"),
        "host": f"{platform.system()} {platform.machine()}",
        "corpus": {"documents": len(docs), "queries": len(queries)},
        "config": {
            "index_version": INDEX_VERSION,
            "embedding": HashingEmbedder().manifest,
            "rrf_k": RRF_K,
            "branch_k": BRANCH_K,
            "top_k": TOP_K,
            "vector_search": "exact cosine scan (no ANN index)",
            "configured_abstain_coverage": configured,
            "tuned_on_dev": tuned,
        },
        "split_leakage_families": leaks,
        "results": {},
    }
    for mode in Mode:
        rows = runs[(mode, configured)]
        report["results"][mode.value] = {
            "dev": summarize(split(rows, "dev")),
            "holdout": summarize(split(rows, "holdout")),
            "all": summarize(rows),
            "dev_objective_by_threshold": {
                str(t): objective(summarize(split(runs[(mode, t)], "dev"))) for t in THRESHOLDS
            },
            "failures_all": failures(rows),
        }
    return report


def revoke(document_id: str, version: int, actor: str, reason: str) -> dict[str, Any]:
    """Withdraw one document version from retrieval (runbook evidence-withdrawn).

    Never deletes: the row stays for audit and for reconstructing past investigations; the
    retrieval filters (published only) exclude it from every new search immediately.
    """
    if not reason.strip() or not actor.strip():
        raise CorpusError("revoke needs --actor and a non-empty --reason")
    with _engine().begin() as conn:
        row = conn.execute(
            update(knowledge_documents)
            .where(
                knowledge_documents.c.document_id == document_id,
                knowledge_documents.c.version == version,
                knowledge_documents.c.review_status != "revoked",
            )
            .values(review_status="revoked")
            .returning(knowledge_documents.c.tenant_scope)
        ).first()
        if row is None:
            return {"document_id": document_id, "version": version, "revoked": False}
        conn.execute(
            insert(audit_entries).values(
                tenant_id=row.tenant_scope,
                actor=actor[:128],
                action="knowledge.revoke",
                resource_type="knowledge_document",
                resource_id=f"{document_id}@{version}"[:256],
                outcome="revoked",
                correlation_id=f"revoke-{document_id}"[:64],
                details={"reason": reason[:500]},
            )
        )
    return {"document_id": document_id, "version": version, "revoked": True}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["ingest", "evaluate", "revoke"])
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--provider-status", type=Path, default=None)
    parser.add_argument("--document-id")
    parser.add_argument("--version", type=int)
    parser.add_argument("--actor", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args(argv)
    if args.command == "revoke" and (args.document_id is None or args.version is None):
        parser.error("revoke needs --document-id and --version")
    if args.command != "revoke" and args.corpus is None:
        parser.error(f"{args.command} needs --corpus")
    try:
        if args.command == "ingest":
            output = ingest(args.corpus, args.provider_status)
        elif args.command == "revoke":
            output = revoke(args.document_id, args.version, args.actor, args.reason)
        else:
            output = evaluate(args.corpus)
    except (CorpusError, StatusError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
