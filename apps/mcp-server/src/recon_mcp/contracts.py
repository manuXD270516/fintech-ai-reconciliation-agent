"""Closed catalog of READ tools (`tools/v1`) with versioned JSON Schemas.

Every input and output schema sets `additionalProperties: false`. Identity, tenant and
scopes never appear as arguments: they come from the server's service credential.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

TOOLS_VERSION = "tools/v1"
PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "fintech-mcp-server"
PROVIDERS = ["prov-alfa", "prov-beta"]
DOC_TYPES = ["provider_doc", "error_codes", "runbook", "procedure"]
RELATIONS = ["same_reference", "same_attempt", "amount_and_time"]
UUID_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
IDENT_PATTERN = "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
CODE_PATTERN = "^[A-Z][0-9]{2}$"


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FORBIDDEN = "FORBIDDEN"
    STALE_SNAPSHOT = "STALE_SNAPSHOT"
    RATE_LIMITED = "RATE_LIMITED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"


RETRYABLE = {ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.TIMEOUT}


class Scope(StrEnum):
    TRANSACTIONS = "transactions:read"
    RECONCILIATION = "reconciliation:read"
    PROVIDERS = "providers:read"
    KNOWLEDGE = "knowledge:read"


def _obj(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


_STR = {"type": "string"}
_NSTR = {"type": ["string", "null"]}
_INT = {"type": "integer"}
_TIME = {"type": "string", "format": "date-time"}
_NTIME = {"type": ["string", "null"], "format": "date-time"}
_CURSOR = {"type": "string", "minLength": 1, "maxLength": 512}
_AS_OF = {"type": "string", "format": "date-time"}
_QUERY = {"type": "string", "minLength": 1, "maxLength": 1000}
_TOP_K = {"type": "integer", "minimum": 1, "maximum": 10}

PROVENANCE = _obj(
    {
        "source_id": _STR,
        "version": _STR,
        "record_or_chunk_id": _STR,
        "content_hash": _STR,
        "locator": _STR,
        "effective_at": _NTIME,
        "synthetic": {"const": True},
    },
    ["source_id", "version", "record_or_chunk_id", "content_hash", "locator", "effective_at",
     "synthetic"],
)  # fmt: skip

TRANSACTION = _obj(
    {
        "transaction_id": _STR,
        "revision": _INT,
        "current_revision": _INT,
        "source": {"enum": ["internal_ledger", "provider_report"]},
        "source_record_id": _STR,
        "provider_id": _STR,
        "merchant_account": _STR,
        "operation_type": _STR,
        "payment_ref": _STR,
        "attempt_ref": _NSTR,
        "amount_minor": _INT,
        "currency": _STR,
        "status": _STR,
        "occurred_at": _TIME,
        "received_at": _TIME,
    },
    ["transaction_id", "revision", "current_revision", "source", "source_record_id",
     "provider_id", "merchant_account", "operation_type", "payment_ref", "attempt_ref",
     "amount_minor", "currency", "status", "occurred_at", "received_at"],
)  # fmt: skip

CANDIDATE = _obj(
    {
        "transaction_id": _STR,
        "source": _STR,
        "payment_ref": _STR,
        "amount_minor": _INT,
        "currency": _STR,
        "status": _STR,
        "occurred_at": _TIME,
        "relations": {"type": "array", "items": {"enum": RELATIONS}},
    },
    ["transaction_id", "source", "payment_ref", "amount_minor", "currency", "status",
     "occurred_at", "relations"],
)  # fmt: skip

RESULT_ROW = _obj(
    {
        "ordinal": _INT,
        "payment_ref": _STR,
        "operation_type": _STR,
        "match_status": _STR,
        "rule": _STR,
        "discrepancy_types": {"type": "array", "items": _STR},
        "amount_difference_minor": {"type": ["integer", "null"]},
        "score": {"type": ["number", "null"]},
        "explanation": _STR,
    },
    ["ordinal", "payment_ref", "operation_type", "match_status", "rule", "discrepancy_types",
     "amount_difference_minor", "score", "explanation"],
)  # fmt: skip

BATCH = _obj(
    {
        "batch_id": _STR,
        "provider_id": _STR,
        "merchant_account": _STR,
        "currency": _STR,
        "window_start": _TIME,
        "window_end": _TIME,
        "business_timezone": _STR,
        "cutoff_at": _TIME,
        "left_source": _STR,
        "right_source": _STR,
        "left_complete": {"type": "boolean"},
        "right_complete": {"type": "boolean"},
        "version": _INT,
    },
    ["batch_id", "provider_id", "merchant_account", "currency", "window_start", "window_end",
     "business_timezone", "cutoff_at", "left_source", "right_source", "left_complete",
     "right_complete", "version"],
)  # fmt: skip

RUN = _obj(
    {
        "run_id": _STR,
        "run_number": _INT,
        "status": _STR,
        "ruleset_version": _STR,
        "snapshot_hash": _NSTR,
        "observation_count": {"type": ["integer", "null"]},
        "completed_at": _NTIME,
        "result_count": _INT,
    },
    ["run_id", "run_number", "status", "ruleset_version", "snapshot_hash", "observation_count",
     "completed_at", "result_count"],
)  # fmt: skip

TOTAL = _obj(
    {"currency": _STR, "source": _STR, "observations": _INT, "amount_minor": _INT},
    ["currency", "source", "observations", "amount_minor"],
)

STATUS = _obj(
    {
        "status": {"enum": ["operational", "degraded", "outage"]},
        "valid_from": _TIME,
        "valid_to": _NTIME,
        "observed_at": _TIME,
        "freshness_seconds": _INT,
        "details": {"type": "object", "additionalProperties": {"type": "string"}},
    },
    ["status", "valid_from", "valid_to", "observed_at", "freshness_seconds", "details"],
)

KNOWLEDGE_ITEM = _obj(
    {
        "citation": _STR,
        "document_id": _STR,
        "version": _INT,
        "chunk_id": _STR,
        "document_type": _STR,
        "title": _STR,
        "section_path": _STR,
        "content": _STR,
        "rrf_score": {"type": "number"},
        "branches": {"type": "array", "items": _STR},
        "untrusted_instructions": {"type": "boolean"},
        "effective_from": _TIME,
    },
    ["citation", "document_id", "version", "chunk_id", "document_type", "title", "section_path",
     "content", "rrf_score", "branches", "untrusted_instructions", "effective_from"],
)  # fmt: skip

KNOWLEDGE_DATA = _obj(
    {
        "ranking": _STR,
        "abstained": {"type": "boolean"},
        "abstention_reason": _NSTR,
        "items": {"type": "array", "items": KNOWLEDGE_ITEM},
    },
    ["ranking", "abstained", "abstention_reason", "items"],
)


def envelope(data_schema: dict[str, Any]) -> dict[str, Any]:
    return _obj(
        {
            "data": data_schema,
            "provenance": {"type": "array", "items": PROVENANCE},
            "snapshot_version": _STR,
            "retrieved_at": _TIME,
            "warnings": {"type": "array", "items": _STR},
            "next_cursor": _NSTR,
            "tools_version": {"const": TOOLS_VERSION},
        },
        ["data", "provenance", "snapshot_version", "retrieved_at", "warnings", "next_cursor",
         "tools_version"],
    )  # fmt: skip


INPUTS: dict[str, dict[str, Any]] = {
    "get_transaction": _obj(
        {
            "transaction_id": {"type": "string", "pattern": UUID_PATTERN},
            "revision": {"type": "integer", "minimum": 1},
        },
        ["transaction_id"],
    ),
    "find_related_transactions": _obj(
        {
            "transaction_id": {"type": "string", "pattern": UUID_PATTERN},
            "relation_types": {
                "type": "array",
                "items": {"enum": RELATIONS},
                "minItems": 1,
                "uniqueItems": True,
            },
            "window_hours": {"type": "integer", "minimum": 1, "maximum": 168},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            "cursor": _CURSOR,
        },
        ["transaction_id"],
    ),
    "get_reconciliation_batch": _obj(
        {
            "batch_id": {"type": "string", "pattern": IDENT_PATTERN},
            "run_id": {"type": "string", "pattern": UUID_PATTERN},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            "cursor": _CURSOR,
        },
        ["batch_id"],
    ),
    "get_provider_status": _obj(
        {"provider_id": {"enum": PROVIDERS}, "as_of": _AS_OF},
        ["provider_id"],
    ),
    "search_incidents": _obj(
        {
            "query": _QUERY,
            "provider_id": {"enum": PROVIDERS},
            "error_code": {"type": "string", "pattern": CODE_PATTERN},
            "as_of": _AS_OF,
            "top_k": _TOP_K,
        },
        ["query"],
    ),
    "search_provider_docs": _obj(
        {
            "query": _QUERY,
            "provider_id": {"enum": PROVIDERS},
            "error_code": {"type": "string", "pattern": CODE_PATTERN},
            "document_types": {
                "type": "array",
                "items": {"enum": DOC_TYPES},
                "minItems": 1,
                "uniqueItems": True,
            },
            "as_of": _AS_OF,
            "top_k": _TOP_K,
        },
        ["query", "provider_id"],
    ),
}

OUTPUTS: dict[str, dict[str, Any]] = {
    "get_transaction": envelope(TRANSACTION),
    "find_related_transactions": envelope(
        _obj(
            {
                "anchor_transaction_id": _STR,
                "candidates": {"type": "array", "items": CANDIDATE},
                "note": _STR,
            },
            ["anchor_transaction_id", "candidates", "note"],
        )
    ),
    "get_reconciliation_batch": envelope(
        _obj(
            {
                "batch": BATCH,
                "run": {"anyOf": [RUN, {"type": "null"}]},
                "totals_by_currency": {"type": "array", "items": TOTAL},
                "results": {"type": "array", "items": RESULT_ROW},
            },
            ["batch", "run", "totals_by_currency", "results"],
        )
    ),
    "get_provider_status": envelope(
        _obj(
            {
                "provider_id": _STR,
                "as_of": _TIME,
                "snapshot": {"anyOf": [STATUS, {"type": "null"}]},
            },
            ["provider_id", "as_of", "snapshot"],
        )
    ),
    "search_incidents": envelope(KNOWLEDGE_DATA),
    "search_provider_docs": envelope(KNOWLEDGE_DATA),
}

DESCRIPTIONS = {
    "get_transaction": "Read one canonical synthetic observation (optionally a revision). "
    "Never returns raw payloads or card data.",
    "find_related_transactions": "List candidate observations related by explicit criteria. "
    "Candidates are not matches.",
    "get_reconciliation_batch": "Read a batch, its completeness, a run and paginated results.",
    "get_provider_status": "Read the synthetic provider status snapshot valid at a time. "
    "It never states the status of a transaction.",
    "search_incidents": "Hybrid search over authorized synthetic incidents with citations.",
    "search_provider_docs": "Hybrid search over authorized provider docs, error codes, "
    "runbooks and procedures with citations.",
}

SCOPES = {
    "get_transaction": Scope.TRANSACTIONS,
    "find_related_transactions": Scope.TRANSACTIONS,
    "get_reconciliation_batch": Scope.RECONCILIATION,
    "get_provider_status": Scope.PROVIDERS,
    "search_incidents": Scope.KNOWLEDGE,
    "search_provider_docs": Scope.KNOWLEDGE,
}

TIMEOUTS = {name: (8.0 if SCOPES[name] is Scope.KNOWLEDGE else 3.0) for name in INPUTS}
CATALOG = tuple(INPUTS)
