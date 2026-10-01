"""Plan = deterministic template per routing reason + model-proposed steps that pass policy.

The model may only add steps from the read catalog, with identifiers already known to the
case and the case's own provider, within the tool-call budget. Everything else is
rejected and recorded; nothing it proposes can widen permissions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from recon_agents.models import READ_TOOLS, CaseSnapshot, Step

QUERIES = {
    "AMOUNT_MISMATCH": "diferencia de importe liquidación neta comisión",
    "STATUS_MISMATCH": "estado rechazado captura confirmación",
    "DUPLICATE_CANDIDATE": "cobro duplicado referencia de comercio",
    "PROCESSING_ERROR": "estado desconocido cuarentena mapping",
}
FORBIDDEN_ARGUMENTS = {"url", "uri", "tenant_id", "tenant", "scope", "scopes", "subject", "sql"}


@dataclass(frozen=True, slots=True)
class Rejection:
    tool: str
    reason: str


def _query(case: CaseSnapshot) -> str:
    for kind, text in QUERIES.items():
        if kind in case.discrepancy_types:
            return text
    return "conciliación diferencia proveedor"


def template(case: CaseSnapshot, reason: str) -> list[Step]:
    steps: list[Step] = []

    def add(tool: str, why: str, **arguments: Any) -> None:
        steps.append(Step(tool, arguments, why, "template"))

    ids = [*case.left_transaction_ids[:1], *case.right_transaction_ids[:1]]
    if reason == "duplicate_context":
        ids = [*case.left_transaction_ids, *case.right_transaction_ids][:3]
    for tx in ids:
        add("get_transaction", "read the observation behind the result", transaction_id=tx)
    if reason == "ambiguous_candidates":
        if case.left_transaction_ids:
            add("find_related_transactions", "list candidates with explicit criteria",
                transaction_id=case.left_transaction_ids[0])  # fmt: skip
        for alt in case.alternatives[:1]:
            add("get_transaction", "read the competing candidate", transaction_id=alt)
    query = _query(case)
    if reason == "unknown_status":
        add("search_provider_docs", "status vocabulary and quarantine procedure",
            query=query, provider_id=case.provider_id,
            document_types=["error_codes", "runbook"])  # fmt: skip
    else:
        add("search_provider_docs", "documented causes and procedures",
            query=query, provider_id=case.provider_id)  # fmt: skip
    if reason in ("needs_context", "duplicate_context"):
        add("search_incidents", "similar historical incidents (context only)",
            query=query, provider_id=case.provider_id)  # fmt: skip
    add("get_provider_status", "platform status when the payment occurred",
        provider_id=case.provider_id, as_of=case.occurred_at)  # fmt: skip
    return steps


def admit(
    proposals: list[dict[str, Any]], case: CaseSnapshot, current: list[Step], max_steps: int
) -> tuple[list[Step], list[Rejection]]:
    accepted: list[Step] = []
    rejected: list[Rejection] = []
    seen = {(s.tool, json.dumps(s.arguments, sort_keys=True)) for s in current}
    for proposal in proposals:
        tool = str(proposal.get("tool", ""))
        args = proposal.get("arguments")
        if tool not in READ_TOOLS:
            rejected.append(Rejection(tool, "tool_not_in_read_catalog"))
            continue
        if not isinstance(args, dict) or FORBIDDEN_ARGUMENTS & {k.lower() for k in args}:
            rejected.append(Rejection(tool, "forbidden_or_malformed_arguments"))
            continue
        if "transaction_id" in args and args["transaction_id"] not in case.known_transaction_ids:
            rejected.append(Rejection(tool, "transaction_not_in_case"))
            continue
        if "provider_id" in args and args["provider_id"] != case.provider_id:
            rejected.append(Rejection(tool, "provider_outside_case"))
            continue
        key = (tool, json.dumps(args, sort_keys=True))
        if key in seen:
            rejected.append(Rejection(tool, "duplicate_step"))
            continue
        if len(current) + len(accepted) >= max_steps:
            rejected.append(Rejection(tool, "tool_budget_exhausted"))
            continue
        seen.add(key)
        accepted.append(Step(tool, dict(args), str(proposal.get("why", ""))[:300], "model"))
    return accepted, rejected
