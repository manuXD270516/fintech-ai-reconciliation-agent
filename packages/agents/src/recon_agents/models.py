"""Investigation data model: case snapshot, plan steps, claims and the draft contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

# Mirrors fintech-mcp-server `tools/v1`; a unit test asserts both catalogs are equal.
READ_TOOLS = (
    "get_transaction",
    "find_related_transactions",
    "get_reconciliation_batch",
    "get_provider_status",
    "search_incidents",
    "search_provider_docs",
)
NEXT_STEPS = ("REQUEST_PROVIDER_INFO", "REQUEST_INTERNAL_INFO", "HUMAN_REVIEW", "WAIT_FOR_SOURCE")
CLAIM_KINDS = ("FACT", "INFERENCE", "HYPOTHESIS")


class State(StrEnum):
    REQUESTED = "REQUESTED"
    NOT_NEEDED = "NOT_NEEDED"
    PLANNED = "PLANNED"
    EXECUTED = "EXECUTED"
    DRAFTED = "DRAFTED"
    ABSTAINED = "ABSTAINED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


TERMINAL = {State.NOT_NEEDED, State.DRAFTED, State.ABSTAINED, State.ESCALATED, State.FAILED}


@dataclass(frozen=True, slots=True)
class CaseSnapshot:
    """Factual input of one investigation (a reconciliation result and its sides)."""

    case_ref: str
    case_version: int
    tenant_id: str
    batch_id: str
    run_id: str
    ordinal: int
    payment_ref: str
    operation_type: str
    match_status: str
    rule: str
    discrepancy_types: tuple[str, ...]
    amount_difference_minor: int | None
    provider_id: str
    merchant_account: str
    currency: str
    occurred_at: str
    left_transaction_ids: tuple[str, ...]
    right_transaction_ids: tuple[str, ...]
    alternatives: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaseSnapshot:
        values = dict(data)
        for key in ("discrepancy_types", "left_transaction_ids", "right_transaction_ids",
                    "alternatives"):  # fmt: skip
            values[key] = tuple(values.get(key, ()))
        return cls(**values)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("discrepancy_types", "left_transaction_ids", "right_transaction_ids",
                    "alternatives"):  # fmt: skip
            data[key] = list(data[key])
        return data

    @property
    def snapshot_hash(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    @property
    def known_transaction_ids(self) -> set[str]:
        return {*self.left_transaction_ids, *self.right_transaction_ids, *self.alternatives}


@dataclass(frozen=True, slots=True)
class Step:
    tool: str
    arguments: dict[str, Any]
    why: str
    origin: str  # "template" or "model"


@dataclass
class StepRecord:
    tool: str
    arguments: dict[str, Any]
    origin: str
    ok: bool
    error_code: str | None = None
    retryable: bool = False
    seconds: float = 0.0
    provenance_ids: list[str] = field(default_factory=list)


@dataclass
class Budget:
    """Initial EXPECTED budget per investigation (docs/04-agents.md)."""

    max_tool_calls: int = 6
    max_generative_calls: int = 4
    max_tokens: int = 16_000
    max_seconds: float = 60.0
    tool_calls: int = 0
    generative_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tokens_estimated: bool = False
    seconds: float = 0.0
    exhausted: list[str] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"tokens": self.tokens}


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    kind: str
    statement: str
    evidence_refs: tuple[str, ...]
    limitations: str
    needed_evidence: str | None = None


DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "claims",
        "contradictions",
        "missing_evidence",
        "recommended_next_step",
        "summary",
    ],
    "properties": {
        "claims": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["claim_id", "kind", "statement", "evidence_refs", "limitations"],
                "properties": {
                    "claim_id": {"type": "string", "maxLength": 32},
                    "kind": {"type": "string"},
                    "statement": {"type": "string", "maxLength": 600},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "limitations": {"type": "string", "maxLength": 400},
                    "needed_evidence": {"type": "string", "maxLength": 400},
                },
            },
        },
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "missing_evidence": {"type": "array", "items": {"type": "string"}},
        "recommended_next_step": {"type": "string"},
        "summary": {"type": "string", "maxLength": 800},
    },
}

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["extra_steps"],
    "properties": {
        "extra_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tool", "arguments", "why"],
                "properties": {
                    "tool": {"type": "string"},
                    "arguments": {"type": "object"},
                    "why": {"type": "string", "maxLength": 300},
                },
            },
        }
    },
}
