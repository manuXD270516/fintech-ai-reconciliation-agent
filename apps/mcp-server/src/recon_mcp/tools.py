"""Tool execution: authorization, validation, budgets, pagination, size cap and audit.

Order of checks for every call: known tool -> rate limit -> scope -> input schema ->
bounded execution (semaphore + per-tool timeout) -> envelope -> size cap -> output
schema self-check -> audit. Resources of another tenant are always NOT_FOUND so their
existence is never revealed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

import anyio
import mcp_types as types
from jsonschema import Draft202012Validator, FormatChecker

from recon_knowledge.retrieval import SearchContext, SearchResult
from recon_mcp.backend import DependencyError, ReadBackend, Record
from recon_mcp.contracts import (
    DOC_TYPES,
    INPUTS,
    OUTPUTS,
    RELATIONS,
    RETRYABLE,
    SCOPES,
    TIMEOUTS,
    TOOLS_VERSION,
    ErrorCode,
)
from recon_mcp.identity import ServiceIdentity

MAX_RESPONSE_BYTES = 64 * 1024
LIST_KEYS = ("candidates", "results", "items")


class UnknownToolError(Exception):
    """Protocol-level error: the tool is not in the closed catalog."""


class ToolError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Limits:
    max_bytes: int = MAX_RESPONSE_BYTES
    calls_per_minute: int = 120
    max_concurrency: int = 2
    timeouts: dict[str, float] = field(default_factory=lambda: dict(TIMEOUTS))


@dataclass(frozen=True, slots=True)
class Outcome:
    data: Record
    provenance: list[Record]
    snapshot: str
    warnings: list[str] = field(default_factory=list)
    next_cursor: str | None = None


def _iso(value: datetime | str | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.astimezone(UTC).isoformat()


def args_digest(name: str, args: Record, drop: tuple[str, ...] = ()) -> str:
    kept = {k: v for k, v in args.items() if k not in drop}
    blob = json.dumps([name, kept], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def relations_for(anchor: Record, other: Record, window_hours: int) -> list[str]:
    found = []
    if other["payment_ref"] == anchor["payment_ref"]:
        found.append("same_reference")
    if anchor.get("attempt_ref") and other.get("attempt_ref") == anchor["attempt_ref"]:
        found.append("same_attempt")
    a, b = anchor["occurred_at"], other["occurred_at"]
    a = datetime.fromisoformat(a) if isinstance(a, str) else a
    b = datetime.fromisoformat(b) if isinstance(b, str) else b
    if other["amount_minor"] == anchor["amount_minor"] and abs(a - b) <= timedelta(
        hours=window_hours
    ):
        found.append("amount_and_time")
    return found


class Cursors:
    """Opaque HMAC-signed cursors bound to tool, arguments, subject and snapshot."""

    def __init__(self, key: bytes, subject: str) -> None:
        self.key = key
        self.subject = subject

    def encode(self, tool: str, args: Record, offset: int, snapshot: str) -> str:
        body = json.dumps(
            {"o": offset, "s": snapshot, "t": tool, "u": self.subject,
             "a": args_digest(tool, args, ("cursor", "limit"))},
            separators=(",", ":"),
        )  # fmt: skip
        payload = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
        return f"{payload}.{self._sign(payload)}"

    def decode(self, tool: str, args: Record, cursor: str, snapshot: str) -> int:
        payload, _, signature = cursor.partition(".")
        if not hmac.compare_digest(signature, self._sign(payload)):
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "cursor is not valid")
        try:
            body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except ValueError:
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "cursor is not valid") from None
        same_call = body.get("a") == args_digest(tool, args, ("cursor", "limit"))
        if body.get("t") != tool or body.get("u") != self.subject or not same_call:
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "cursor belongs to another request")
        if body.get("s") != snapshot:
            raise ToolError(ErrorCode.STALE_SNAPSHOT, "data changed since the cursor was issued")
        return int(body["o"])

    def _sign(self, payload: str) -> str:
        return hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()[:32]


class ToolService:
    def __init__(
        self,
        backend: ReadBackend,
        identity: ServiceIdentity,
        limits: Limits | None = None,
        cursor_key: bytes | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.backend = backend
        self.identity = identity
        self.limits = limits or Limits()
        self.cursors = Cursors(cursor_key or os.urandom(32), identity.subject)
        self.clock = clock
        self._calls: deque[float] = deque()
        self._semaphore = anyio.Semaphore(self.limits.max_concurrency)
        self.in_flight = 0
        self.max_in_flight = 0
        self._validators = {
            name: Draft202012Validator(schema, format_checker=FormatChecker())
            for name, schema in INPUTS.items()
        }
        self._output_validators = {
            name: Draft202012Validator(schema, format_checker=FormatChecker())
            for name, schema in OUTPUTS.items()
        }
        self._handlers: dict[str, Callable[[Record], Outcome]] = {
            "get_transaction": self._get_transaction,
            "find_related_transactions": self._find_related,
            "get_reconciliation_batch": self._get_batch,
            "get_provider_status": self._provider_status,
            "search_incidents": partial(self._search, ("incident",)),
            "search_provider_docs": partial(self._search, None),
        }

    # --- entry point ------------------------------------------------------------------

    async def call(self, name: str, arguments: Record | None) -> types.CallToolResult:
        if name not in self._handlers:
            raise UnknownToolError(name)
        args = dict(arguments or {})
        correlation = uuid.uuid4().hex[:16]
        started = time.perf_counter()
        try:
            self._check_rate()
            if SCOPES[name] not in self.identity.scopes:
                raise ToolError(ErrorCode.FORBIDDEN, f"scope {SCOPES[name].value} not granted")
            errors = sorted(self._validators[name].iter_errors(args), key=lambda e: e.path)
            if errors:
                where = "/".join(str(p) for p in errors[0].absolute_path) or "arguments"
                raise ToolError(ErrorCode.INVALID_ARGUMENT, f"{where}: {errors[0].message}"[:300])
            outcome = await self._bounded(name, args)
            envelope = self._envelope(name, outcome)
        except ToolError as exc:
            self._audit(name, args, exc.code.value, started, correlation, [])
            return self._error(exc.code, exc.message, correlation)
        self._audit(
            name, args, "ok", started, correlation,
            [p["record_or_chunk_id"] for p in envelope["provenance"]],
        )  # fmt: skip
        text = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
        return types.CallToolResult(
            content=[types.TextContent(text=text)], structured_content=envelope
        )

    def _check_rate(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > 60:
            self._calls.popleft()
        if len(self._calls) >= self.limits.calls_per_minute:
            raise ToolError(ErrorCode.RATE_LIMITED, "per-subject rate limit exceeded")
        self._calls.append(now)

    async def _bounded(self, name: str, args: Record) -> Outcome:
        async with self._semaphore:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            try:
                with anyio.fail_after(self.limits.timeouts[name]):
                    return await anyio.to_thread.run_sync(
                        self._handlers[name], args, abandon_on_cancel=True
                    )
            except TimeoutError:
                raise ToolError(ErrorCode.TIMEOUT, f"{name} exceeded its time budget") from None
            except DependencyError:
                raise ToolError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE, "a backing store is unavailable"
                ) from None
            finally:
                self.in_flight -= 1

    def _envelope(self, name: str, outcome: Outcome) -> Record:
        envelope: Record = {
            "data": outcome.data,
            "provenance": outcome.provenance,
            "snapshot_version": outcome.snapshot,
            "retrieved_at": _iso(self.clock()),
            "warnings": list(outcome.warnings),
            "next_cursor": outcome.next_cursor,
            "tools_version": TOOLS_VERSION,
        }
        size = len(json.dumps(envelope, ensure_ascii=False).encode())
        if size > self.limits.max_bytes:
            envelope = self._truncate(envelope)
        problems = list(self._output_validators[name].iter_errors(envelope))
        if problems:  # a server bug: never send a response that breaks its own contract
            raise RuntimeError(f"{name} produced an invalid response: {problems[0].message}")
        return envelope

    def _truncate(self, envelope: Record) -> Record:
        key = next((k for k in LIST_KEYS if isinstance(envelope["data"].get(k), list)), None)
        if key is None:
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "response exceeds the size limit")
        items: list[Any] = envelope["data"][key]
        dropped = 0
        while items and len(json.dumps(envelope, ensure_ascii=False).encode()) > (
            self.limits.max_bytes
        ):
            items.pop()
            dropped += 1
        kept_ids = {i.get("chunk_id") or i.get("transaction_id") for i in items}
        envelope["provenance"] = [
            p for p in envelope["provenance"]
            if key == "results" or p["record_or_chunk_id"] in kept_ids
        ]  # fmt: skip
        envelope["warnings"].append(
            f"truncated: {dropped} whole item(s) omitted to stay under {self.limits.max_bytes} "
            "bytes; no citation was cut"
        )
        return envelope

    def _error(self, code: ErrorCode, message: str, correlation: str) -> types.CallToolResult:
        payload = {
            "error": {
                "code": code.value,
                "message": message,
                "retryable": code in RETRYABLE,
                "correlation_id": correlation,
            }
        }
        return types.CallToolResult(
            content=[types.TextContent(text=json.dumps(payload))],
            structured_content=payload,
            is_error=True,
        )

    def _audit(
        self,
        name: str,
        args: Record,
        outcome: str,
        started: float,
        correlation: str,
        refs: list[str],
    ) -> None:
        entry = {
            "tenant_id": self.identity.tenant_id,
            "actor": self.identity.subject,
            "tool": name,
            "args_sha256": args_digest(name, args),
            "outcome": outcome,
            "duration_ms": round(1000 * (time.perf_counter() - started), 2),
            "correlation_id": correlation,
            "refs": refs[:20],
        }
        try:
            self.backend.audit(entry)
        except DependencyError:
            pass  # telemetry/audit outage must not turn a read into a write failure

    # --- helpers ----------------------------------------------------------------------

    def _page(
        self, tool: str, args: Record, rows: list[Record], snapshot: str, default: int
    ) -> tuple[list[Record], str | None]:
        offset = 0
        if "cursor" in args:
            offset = self.cursors.decode(tool, args, args["cursor"], snapshot)
        limit = int(args.get("limit", default))
        page = rows[offset : offset + limit]
        more = offset + limit < len(rows)
        cursor = self.cursors.encode(tool, args, offset + limit, snapshot) if more else None
        return page, cursor

    @staticmethod
    def _tx_provenance(rec: Record) -> Record:
        return {
            "source_id": f"observation/{rec['source']}",
            "version": str(rec["revision"]),
            "record_or_chunk_id": rec["transaction_id"],
            "content_hash": rec["raw_hash"],
            "locator": f"{rec['source']}/{rec['source_record_id']}@{rec['revision']}",
            "effective_at": _iso(rec["occurred_at"]),
            "synthetic": True,
        }

    def _as_of(self, args: Record) -> datetime:
        if "as_of" not in args:
            return self.clock()
        value = datetime.fromisoformat(args["as_of"])
        if value.tzinfo is None:
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "as_of needs an explicit offset")
        return value

    # --- handlers (run in a worker thread) ----------------------------------------------

    def _get_transaction(self, args: Record) -> Outcome:
        tenant = self.identity.tenant_id
        rec = self.backend.find_transaction(tenant, args["transaction_id"], args.get("revision"))
        if rec is None:
            raise ToolError(ErrorCode.NOT_FOUND, "transaction not found")
        fields = (
            "transaction_id", "revision", "current_revision", "source", "source_record_id",
            "provider_id", "merchant_account", "operation_type", "payment_ref", "attempt_ref",
            "amount_minor", "currency", "status",
        )  # fmt: skip
        data = {k: rec[k] for k in fields} | {
            "occurred_at": _iso(rec["occurred_at"]),
            "received_at": _iso(rec["received_at"]),
        }
        warnings = []
        if rec["revision"] != rec["current_revision"]:
            warnings.append(
                f"revision {rec['revision']} is not current ({rec['current_revision']})"
            )
        snapshot = self.backend.snapshot_version(tenant, "transactions")
        return Outcome(data, [self._tx_provenance(rec)], snapshot, warnings)

    def _find_related(self, args: Record) -> Outcome:
        tenant = self.identity.tenant_id
        anchor = self.backend.find_transaction(tenant, args["transaction_id"], None)
        if anchor is None:
            raise ToolError(ErrorCode.NOT_FOUND, "transaction not found")
        window = int(args.get("window_hours", 24))
        wanted = set(args.get("relation_types", RELATIONS))
        candidates = []
        for other in self.backend.related_candidates(tenant, anchor, window):
            relations = [r for r in relations_for(anchor, other, window) if r in wanted]
            if relations:
                candidates.append((other, relations))
        candidates.sort(
            key=lambda c: (-len(c[1]), _iso(c[0]["occurred_at"]), c[0]["transaction_id"])
        )
        snapshot = self.backend.snapshot_version(tenant, "transactions")
        rows = [
            {
                "transaction_id": o["transaction_id"],
                "source": o["source"],
                "payment_ref": o["payment_ref"],
                "amount_minor": o["amount_minor"],
                "currency": o["currency"],
                "status": o["status"],
                "occurred_at": _iso(o["occurred_at"]),
                "relations": rel,
                "_prov": self._tx_provenance(o),
            }
            for o, rel in candidates
        ]
        page, cursor = self._page("find_related_transactions", args, rows, snapshot, 10)
        provenance = [self._tx_provenance(anchor)] + [r.pop("_prov") for r in page]
        data = {
            "anchor_transaction_id": anchor["transaction_id"],
            "candidates": page,
            "note": "related by the listed criteria only; candidates are not matches",
        }
        return Outcome(data, provenance, snapshot, [], cursor)

    def _get_batch(self, args: Record) -> Outcome:
        tenant = self.identity.tenant_id
        batch = self.backend.find_batch(tenant, args["batch_id"])
        if batch is None:
            raise ToolError(ErrorCode.NOT_FOUND, "batch not found")
        run = self.backend.find_run(tenant, args["batch_id"], args.get("run_id"))
        if run is None and "run_id" in args:
            raise ToolError(ErrorCode.NOT_FOUND, "run not found")
        results = self.backend.run_results(run["run_id"]) if run else []
        snapshot = (run or {}).get("snapshot_hash") or f"batch-v{batch['version']}"
        page, cursor = self._page("get_reconciliation_batch", args, results, snapshot, 20)
        batch_fields = (
            "batch_id", "provider_id", "merchant_account", "currency", "business_timezone",
            "left_source", "right_source", "left_complete", "right_complete", "version",
        )  # fmt: skip
        data = {
            "batch": {k: batch[k] for k in batch_fields}
            | {k: _iso(batch[k]) for k in ("window_start", "window_end", "cutoff_at")},
            "run": None
            if run is None
            else {
                "run_id": str(run["run_id"]),
                "run_number": run["run_number"],
                "status": run["status"],
                "ruleset_version": run["ruleset_version"],
                "snapshot_hash": run["snapshot_hash"],
                "observation_count": run["observation_count"],
                "completed_at": _iso(run["completed_at"]),
                "result_count": len(results),
            },
            "totals_by_currency": self.backend.batch_totals(tenant, batch),
            "results": page,
        }
        provenance = [
            {
                "source_id": "reconciliation_batch",
                "version": str(batch["version"]),
                "record_or_chunk_id": batch["batch_id"],
                "content_hash": hashlib.sha256(
                    json.dumps(data["batch"], sort_keys=True).encode()
                ).hexdigest(),
                "locator": f"batch/{batch['batch_id']}",
                "effective_at": _iso(batch["window_start"]),
                "synthetic": True,
            }
        ]
        if run is not None:
            provenance.append(
                {
                    "source_id": "reconciliation_run",
                    "version": str(run["run_number"]),
                    "record_or_chunk_id": str(run["run_id"]),
                    "content_hash": run["snapshot_hash"] or "",
                    "locator": f"run/{run['run_id']}",
                    "effective_at": _iso(run["completed_at"]),
                    "synthetic": True,
                }
            )
        warnings = []
        if run is None:
            warnings.append("no completed run for this batch")
        if not (batch["left_complete"] and batch["right_complete"]):
            warnings.append("source completeness not confirmed; missing items may still arrive")
        return Outcome(data, provenance, snapshot, warnings, cursor)

    def _provider_status(self, args: Record) -> Outcome:
        as_of = self._as_of(args)
        snap = self.backend.provider_status(args["provider_id"], as_of)
        data: Record = {"provider_id": args["provider_id"], "as_of": _iso(as_of), "snapshot": None}
        if snap is None:
            return Outcome(data, [], "provider-status", ["no snapshot valid at as_of"])
        observed = snap["observed_at"]
        observed = datetime.fromisoformat(observed) if isinstance(observed, str) else observed
        data["snapshot"] = {
            "status": snap["status"],
            "valid_from": _iso(snap["valid_from"]),
            "valid_to": _iso(snap["valid_to"]),
            "observed_at": _iso(observed),
            "freshness_seconds": max(0, int((as_of - observed).total_seconds())),
            "details": {str(k): str(v) for k, v in dict(snap.get("details") or {}).items()},
        }
        version = str(snap.get("source_version", "provider-status"))
        provenance = [
            {
                "source_id": f"provider_status/{args['provider_id']}",
                "version": version,
                "record_or_chunk_id": f"{args['provider_id']}@{_iso(snap['valid_from'])}",
                "content_hash": hashlib.sha256(
                    json.dumps(data["snapshot"], sort_keys=True).encode()
                ).hexdigest(),
                "locator": f"valid {_iso(snap['valid_from'])} .. {_iso(snap['valid_to'])}",
                "effective_at": _iso(snap["valid_from"]),
                "synthetic": True,
            }
        ]
        return Outcome(data, provenance, version, ["platform status only; not a transaction state"])

    def _search(self, fixed_types: tuple[str, ...] | None, args: Record) -> Outcome:
        ctx = SearchContext(
            tenant_id=self.identity.tenant_id,
            roles=self.identity.knowledge_roles,
            as_of=self._as_of(args),
            provider_id=args.get("provider_id"),
        )
        query = args["query"] + (f" {args['error_code']}" if "error_code" in args else "")
        types_ = fixed_types or tuple(args.get("document_types", DOC_TYPES))
        result: SearchResult = self.backend.search(query, ctx, types_, int(args.get("top_k", 5)))
        items = [
            {
                "citation": h.citation,
                "document_id": h.document_id,
                "version": h.version,
                "chunk_id": h.chunk_id,
                "document_type": h.document_type,
                "title": h.title,
                "section_path": h.section_path,
                "content": h.content,
                "rrf_score": h.rrf_score,
                "branches": list(h.branches),
                "untrusted_instructions": h.flagged_instructions,
                "effective_from": _iso(h.effective_from),
            }
            for h in result.hits
        ]
        provenance = [
            {
                "source_id": h.document_id,
                "version": str(h.version),
                "record_or_chunk_id": h.chunk_id,
                "content_hash": h.content_hash,
                "locator": h.locator,
                "effective_at": _iso(h.effective_from),
                "synthetic": True,
            }
            for h in result.hits
        ]
        warnings = list(result.warnings)
        if result.abstained:
            warnings.append(f"abstained: {result.reason}")
        data = {
            "ranking": result.ranking,
            "abstained": result.abstained,
            "abstention_reason": result.reason,
            "items": items,
        }
        return Outcome(data, provenance, f"knowledge:{ctx.as_of.date().isoformat()}", warnings)
