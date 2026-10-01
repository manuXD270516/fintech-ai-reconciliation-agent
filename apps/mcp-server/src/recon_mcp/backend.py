"""Read backends of the MCP server.

`ReadBackend` is what the tools need. `SqlBackend` (sql_backend.py) is the real one.
`MemoryBackend` serves a JSON fixture for protocol/contract tests and offline demos; its
knowledge search is a simple term-overlap ranking, NOT the hybrid retrieval of M3.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from recon_knowledge.retrieval import (
    Hit,
    Mode,
    SearchContext,
    SearchResult,
    abstention,
    terms,
)

Record = dict[str, Any]


class DependencyError(Exception):
    """A backing store failed; never reported as an empty result."""


class ReadBackend(Protocol):
    def find_transaction(
        self, tenant_id: str, transaction_id: str, revision: int | None
    ) -> Record | None: ...

    def related_candidates(
        self, tenant_id: str, anchor: Record, window_hours: int
    ) -> list[Record]: ...

    def find_batch(self, tenant_id: str, batch_id: str) -> Record | None: ...

    def find_run(self, tenant_id: str, batch_id: str, run_id: str | None) -> Record | None: ...

    def run_results(self, run_id: str) -> list[Record]: ...

    def batch_totals(self, tenant_id: str, batch: Record) -> list[Record]: ...

    def provider_status(self, provider_id: str, as_of: datetime) -> Record | None: ...

    def search(
        self, query: str, ctx: SearchContext, document_types: tuple[str, ...], top_k: int
    ) -> SearchResult: ...

    def snapshot_version(self, tenant_id: str, scope: str) -> str: ...

    def audit(self, entry: Record) -> None: ...


def _ts(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


class MemoryBackend:
    """In-memory fixture backend. `delay` and `fail` let tests inject latency and outages."""

    def __init__(self, data: Record) -> None:
        self.data = data
        self.delay = 0.0
        self.fail = False
        self.audits: list[Record] = []

    @classmethod
    def from_file(cls, path: Path) -> MemoryBackend:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def _io(self) -> None:
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise DependencyError("fixture backend unavailable")

    def find_transaction(
        self, tenant_id: str, transaction_id: str, revision: int | None
    ) -> Record | None:
        self._io()
        rows = [
            t
            for t in self.data["transactions"]
            if t["tenant_id"] == tenant_id and t["transaction_id"] == transaction_id
        ]
        if not rows:
            return None
        current = max(r["revision"] for r in rows)
        wanted = current if revision is None else revision
        row = next((r for r in rows if r["revision"] == wanted), None)
        return None if row is None else row | {"current_revision": current}

    def related_candidates(self, tenant_id: str, anchor: Record, window_hours: int) -> list[Record]:
        self._io()
        latest: dict[str, Record] = {}
        for t in self.data["transactions"]:
            same_scope = all(
                t[k] == anchor[k]
                for k in ("tenant_id", "provider_id", "merchant_account", "currency")
            )
            if not same_scope or t["transaction_id"] == anchor["transaction_id"]:
                continue
            if t["revision"] >= latest.get(t["transaction_id"], {"revision": 0})["revision"]:
                latest[t["transaction_id"]] = t
        return list(latest.values())

    def find_batch(self, tenant_id: str, batch_id: str) -> Record | None:
        self._io()
        return next(
            (
                b
                for b in self.data["batches"]
                if b["tenant_id"] == tenant_id and b["batch_id"] == batch_id
            ),
            None,
        )

    def find_run(self, tenant_id: str, batch_id: str, run_id: str | None) -> Record | None:
        self._io()
        runs = [
            r
            for r in self.data["runs"]
            if r["tenant_id"] == tenant_id and r["batch_id"] == batch_id
        ]
        if run_id is not None:
            return next((r for r in runs if r["run_id"] == run_id), None)
        done = [r for r in runs if r["status"] == "completed"]
        return max(done, key=lambda r: r["run_number"]) if done else None

    def run_results(self, run_id: str) -> list[Record]:
        self._io()
        return list(self.data["results"].get(run_id, []))

    def batch_totals(self, tenant_id: str, batch: Record) -> list[Record]:
        self._io()
        return list(batch.get("totals", []))

    def provider_status(self, provider_id: str, as_of: datetime) -> Record | None:
        self._io()
        for snap in self.data["provider_status"]:
            start, end = _ts(snap["valid_from"]), _ts(snap["valid_to"])
            if snap["provider_id"] != provider_id or start is None:
                continue
            if start <= as_of and (end is None or as_of < end):
                return dict(snap)
        return None

    def search(
        self, query: str, ctx: SearchContext, document_types: tuple[str, ...], top_k: int
    ) -> SearchResult:
        self._io()
        wanted = terms(query)
        scored = []
        for c in self.data["chunks"]:
            allowed = (
                c["review_status"] == "published"
                and c["tenant_scope"] in ("global", ctx.tenant_id)
                and bool(set(c["acl"]) & set(ctx.roles))
                and (ctx.provider_id is None or c["provider_id"] in (None, ctx.provider_id))
                and c["document_type"] in document_types
                and (_ts(c["effective_from"]) or ctx.as_of) <= ctx.as_of
            )
            overlap = len(wanted & terms(f"{c['title']} {c['content']}"))
            if allowed and overlap:
                scored.append((overlap, c))
        scored.sort(key=lambda sc: (-sc[0], sc[1]["chunk_id"]))
        hits = tuple(
            Hit(
                chunk_id=c["chunk_id"],
                document_id=c["document_id"],
                version=c["version"],
                section_slug=c["section_slug"],
                section_path=c["section_path"],
                title=c["title"],
                content=c["content"],
                content_hash=c["content_hash"],
                start_line=c["start_line"],
                end_line=c["end_line"],
                effective_from=datetime.fromisoformat(c["effective_from"]),
                rrf_score=float(score),
                branches=("fixture-term-overlap",),
                flagged_instructions=c["flagged_instructions"],
                document_type=c["document_type"],
            )
            for score, c in scored[:top_k]
        )
        reason = abstention(query, hits)
        if reason is not None:
            return SearchResult(Mode.HYBRID, (), True, reason, (), "fixture-term-overlap")
        warnings = tuple(
            f"untrusted_instructions:{h.chunk_id}" for h in hits if h.flagged_instructions
        )
        return SearchResult(Mode.HYBRID, hits, False, None, warnings, "fixture-term-overlap")

    def snapshot_version(self, tenant_id: str, scope: str) -> str:
        self._io()
        return str(self.data.get("snapshot", {}).get(scope, "fixture-1"))

    def audit(self, entry: Record) -> None:
        self.audits.append(entry)
