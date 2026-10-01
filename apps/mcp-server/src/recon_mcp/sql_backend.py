"""PostgreSQL backend used with the read-only `recon_mcp` role.

The role can SELECT evidence tables and INSERT audit entries; every query is
parameterized and filtered by the tenant of the service identity.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, RowMapping, func, select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import DBAPIError

from recon_knowledge.repository import KnowledgeRepository
from recon_knowledge.retrieval import Mode, SearchContext, SearchResult
from recon_mcp.backend import DependencyError, Record
from recon_store.engine import runtime_engine, runtime_url
from recon_store.tables import (
    batches,
    observations,
    provider_status,
    results,
    runs,
)

_AUDIT_INSERT = text(
    "INSERT INTO recon.audit_entries (tenant_id, actor, action, resource_type, resource_id, "
    "outcome, correlation_id, details) VALUES (:tenant_id, :actor, :action, 'mcp_tool', "
    ":resource_id, :outcome, :correlation_id, CAST(:details AS jsonb))"
)

_TX_COLUMNS = (
    observations.c.transaction_uid,
    observations.c.tenant_id,
    observations.c.revision,
    observations.c.source,
    observations.c.source_record_id,
    observations.c.provider_id,
    observations.c.merchant_account,
    observations.c.operation_type,
    observations.c.payment_ref,
    observations.c.attempt_ref,
    observations.c.amount_minor,
    observations.c.currency,
    observations.c.status,
    observations.c.occurred_at,
    observations.c.received_at,
    observations.c.raw_hash,
)


def _tx(row: RowMapping, current: int) -> Record:
    rec = dict(row)
    rec["transaction_id"] = str(rec.pop("transaction_uid"))
    rec["current_revision"] = current
    return rec


class SqlBackend:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.knowledge = KnowledgeRepository(engine)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> SqlBackend:
        return cls(
            runtime_engine(
                runtime_url(
                    env["MCP_DB_HOST"],
                    int(env.get("MCP_DB_PORT", "5432")),
                    env["MCP_DB_NAME"],
                    env["MCP_DB_USER"],
                    env["MCP_DB_PASSWORD"],
                ),
                pool_size=2,
            )
        )

    def _rows(self, stmt: Any) -> list[RowMapping]:
        try:
            with self.engine.connect() as conn:
                return list(conn.execute(stmt).mappings())
        except DBAPIError as exc:
            raise DependencyError(type(exc.orig).__name__) from None

    def find_transaction(
        self, tenant_id: str, transaction_id: str, revision: int | None
    ) -> Record | None:
        rows = self._rows(
            select(*_TX_COLUMNS)
            .where(
                observations.c.tenant_id == tenant_id,
                observations.c.transaction_uid == uuid.UUID(transaction_id),
            )
            .order_by(observations.c.revision)
        )
        if not rows:
            return None
        current = max(r["revision"] for r in rows)
        wanted = current if revision is None else revision
        row = next((r for r in rows if r["revision"] == wanted), None)
        return None if row is None else _tx(row, current)

    def related_candidates(self, tenant_id: str, anchor: Record, window_hours: int) -> list[Record]:
        occurred: datetime = anchor["occurred_at"]
        window = timedelta(hours=window_hours)
        latest = (
            select(*_TX_COLUMNS)
            .where(
                observations.c.tenant_id == tenant_id,
                observations.c.provider_id == anchor["provider_id"],
                observations.c.merchant_account == anchor["merchant_account"],
                observations.c.currency == anchor["currency"],
                observations.c.transaction_uid != uuid.UUID(anchor["transaction_id"]),
                (observations.c.payment_ref == anchor["payment_ref"])
                | (observations.c.attempt_ref == anchor["attempt_ref"])
                | observations.c.occurred_at.between(occurred - window, occurred + window),
            )
            .order_by(observations.c.transaction_uid, observations.c.revision.desc())
            .ext(distinct_on(observations.c.transaction_uid))
            .limit(500)
        )
        return [_tx(r, r["revision"]) for r in self._rows(latest)]

    def find_batch(self, tenant_id: str, batch_id: str) -> Record | None:
        rows = self._rows(
            select(batches).where(batches.c.tenant_id == tenant_id, batches.c.batch_id == batch_id)
        )
        return dict(rows[0]) if rows else None

    def find_run(self, tenant_id: str, batch_id: str, run_id: str | None) -> Record | None:
        stmt = select(runs).where(runs.c.tenant_id == tenant_id, runs.c.batch_id == batch_id)
        if run_id is not None:
            stmt = stmt.where(runs.c.id == uuid.UUID(run_id))
        else:
            stmt = stmt.where(runs.c.status == "completed").order_by(runs.c.run_number.desc())
        rows = self._rows(stmt.limit(1))
        if not rows:
            return None
        run = dict(rows[0])
        run["run_id"] = str(run.pop("id"))
        return run

    def run_results(self, run_id: str) -> list[Record]:
        rows = self._rows(
            select(
                results.c.ordinal,
                results.c.payment_ref,
                results.c.operation_type,
                results.c.match_status,
                results.c.rule,
                results.c.discrepancy_types,
                results.c.amount_difference_minor,
                results.c.score,
                results.c.explanation,
            )
            .where(results.c.run_id == uuid.UUID(run_id))
            .order_by(results.c.ordinal)
        )
        out = []
        for r in rows:
            rec = dict(r)
            rec["discrepancy_types"] = list(rec["discrepancy_types"])
            rec["score"] = None if rec["score"] is None else float(rec["score"])
            out.append(rec)
        return out

    def batch_totals(self, tenant_id: str, batch: Record) -> list[Record]:
        latest = (
            select(observations.c.source, observations.c.amount_minor, observations.c.currency)
            .where(
                observations.c.tenant_id == tenant_id,
                observations.c.provider_id == batch["provider_id"],
                observations.c.merchant_account == batch["merchant_account"],
                observations.c.currency == batch["currency"],
                observations.c.occurred_at >= batch["window_start"],
                observations.c.occurred_at < batch["window_end"],
            )
            .order_by(observations.c.transaction_uid, observations.c.revision.desc())
            .ext(distinct_on(observations.c.transaction_uid))
            .subquery()
        )
        rows = self._rows(
            select(
                latest.c.currency,
                latest.c.source,
                func.count().label("observations"),
                func.coalesce(func.sum(latest.c.amount_minor), 0).label("amount_minor"),
            )
            .group_by(latest.c.currency, latest.c.source)
            .order_by(latest.c.source)
        )
        return [
            {
                **dict(r),
                "observations": int(r["observations"]),
                "amount_minor": int(r["amount_minor"]),
            }
            for r in rows
        ]

    def provider_status(self, provider_id: str, as_of: datetime) -> Record | None:
        rows = self._rows(
            select(provider_status)
            .where(
                provider_status.c.provider_id == provider_id,
                provider_status.c.valid_from <= as_of,
                (provider_status.c.valid_to.is_(None)) | (provider_status.c.valid_to > as_of),
            )
            .order_by(provider_status.c.valid_from.desc())
            .limit(1)
        )
        return dict(rows[0]) if rows else None

    def search(
        self, query: str, ctx: SearchContext, document_types: tuple[str, ...], top_k: int
    ) -> SearchResult:
        try:
            return self.knowledge.search(
                query, ctx, Mode.HYBRID, top_k=top_k, document_types=document_types
            )
        except DBAPIError as exc:
            raise DependencyError(type(exc.orig).__name__) from None

    def snapshot_version(self, tenant_id: str, scope: str) -> str:
        rows = self._rows(
            select(func.coalesce(func.max(observations.c.id), 0).label("m")).where(
                observations.c.tenant_id == tenant_id
            )
        )
        return f"observations@{rows[0]['m']}"

    def audit(self, entry: Record) -> None:
        try:
            # Plain INSERT without RETURNING: the role has INSERT but no SELECT on audit.
            with self.engine.begin() as conn:
                conn.execute(
                    _AUDIT_INSERT,
                    {
                        "tenant_id": entry["tenant_id"],
                        "actor": entry["actor"],
                        "action": f"mcp.{entry['tool']}"[:64],
                        "resource_id": entry["tool"],
                        "outcome": entry["outcome"],
                        "correlation_id": entry["correlation_id"],
                        "details": json.dumps(
                            {
                                "args_sha256": entry["args_sha256"],
                                "duration_ms": entry["duration_ms"],
                                "refs": entry["refs"],
                            }
                        ),
                    },
                )
        except DBAPIError as exc:
            raise DependencyError(type(exc.orig).__name__) from None
