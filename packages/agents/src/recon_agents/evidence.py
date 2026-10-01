"""Deterministic evidence phase (docs/04: Evidence as a verifier, not another agent).

1. `collect` turns tool payloads into record facts and document excerpts, each with a
   resolvable reference. Facts are computed by code (amounts, differences, statuses).
2. `verify` checks the model's claims: allowed kind, resolvable citations, FACTs backed by
   records (a document saying X is not proof X happened to this payment), numbers present in
   the cited records, and an allowed next step. Hypotheses are never promoted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from recon_agents.models import CLAIM_KINDS, DRAFT_SCHEMA, NEXT_STEPS, CaseSnapshot, Claim
from recon_agents.tool_client import ToolOutcome

RECORD_PREFIXES = ("tx:", "status:", "batch:", "calc:")
_NUMBER = re.compile(r"-?\d{3,}")
EXCERPT_CHARS = 700


@dataclass
class Bundle:
    facts: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def refs(self) -> set[str]:
        return set(self.provenance)

    def numbers(self, refs: tuple[str, ...]) -> set[str]:
        found: set[str] = set()
        for fact in self.facts:
            if set(fact["evidence_refs"]) & set(refs):
                found |= set(_NUMBER.findall(fact["statement"]))
        return found


def _role(case: CaseSnapshot, tx_id: str) -> str:
    if tx_id in case.left_transaction_ids:
        return "left_transaction"
    if tx_id in case.right_transaction_ids:
        return "right_transaction"
    return "candidate"


def collect(case: CaseSnapshot, outcomes: list[tuple[str, dict[str, Any], ToolOutcome]]) -> Bundle:
    bundle = Bundle()
    sides: dict[str, dict[str, Any]] = {}
    for tool, _args, outcome in outcomes:
        if not outcome.ok:
            bundle.gaps.append(f"{tool} sin evidencia: {outcome.error_code}")
            continue
        data, prov = outcome.payload["data"], outcome.payload["provenance"]
        bundle.warnings += outcome.payload.get("warnings", [])
        if tool == "get_transaction":
            ref = f"tx:{data['transaction_id']}@{data['revision']}"
            role = _role(case, data["transaction_id"])
            bundle.provenance[ref] = prov[0]
            fact = {
                "evidence_ref": ref,
                "evidence_refs": [ref],
                "role": role,
                "amount_minor": data["amount_minor"],
                "currency": data["currency"],
                "statement": (
                    f"{data['source']} registra {data['payment_ref']} ({data['operation_type']}) "
                    f"por {data['amount_minor']} {data['currency']} en unidades menores, estado "
                    f"{data['status']}, revisión {data['revision']}."
                ),
            }
            bundle.facts.append(fact)
            if role in ("left_transaction", "right_transaction"):
                sides[role] = fact
        elif tool == "find_related_transactions":
            for item, item_prov in zip(data["candidates"], prov[1:], strict=False):
                ref = f"tx:{item['transaction_id']}@{item_prov['version']}"
                bundle.provenance[ref] = item_prov
                bundle.facts.append(
                    {
                        "evidence_ref": ref,
                        "evidence_refs": [ref],
                        "role": "candidate",
                        "amount_minor": item["amount_minor"],
                        "currency": item["currency"],
                        "statement": (
                            f"Candidato {item['payment_ref']} de {item['source']} por "
                            f"{item['amount_minor']} {item['currency']}, relacionado por "
                            f"{', '.join(item['relations'])} (no es un match)."
                        ),
                    }
                )
        elif tool == "get_provider_status" and data["snapshot"] is not None:
            snap = data["snapshot"]
            ref = f"status:{prov[0]['record_or_chunk_id']}"
            bundle.provenance[ref] = prov[0]
            bundle.facts.append(
                {
                    "evidence_ref": ref,
                    "evidence_refs": [ref],
                    "role": "provider_status",
                    "statement": (
                        f"Estado de plataforma de {data['provider_id']} a {data['as_of']}: "
                        f"{snap['status']} (no describe una transacción)."
                    ),
                }
            )
        elif tool == "get_provider_status":
            bundle.gaps.append(f"sin snapshot de estado de {data['provider_id']} a {data['as_of']}")
        elif tool in ("search_provider_docs", "search_incidents"):
            if data["abstained"]:
                reason = data["abstention_reason"]
                bundle.gaps.append(f"{tool}: sin evidencia documental ({reason})")
            for item, item_prov in zip(data["items"], prov, strict=False):
                ref = f"doc:{item['document_id']}@{item['version']}#{item['chunk_id']}"
                bundle.provenance[ref] = item_prov
                bundle.documents.append(
                    {
                        "evidence_ref": ref,
                        "document_type": item["document_type"],
                        "title": item["title"],
                        "section_path": item["section_path"],
                        "untrusted_instructions": item["untrusted_instructions"],
                        "content": item["content"][:EXCERPT_CHARS],
                    }
                )
    left, right = sides.get("left_transaction"), sides.get("right_transaction")
    if left and right and left["currency"] == right["currency"]:
        ref = "calc:difference"
        diff = right["amount_minor"] - left["amount_minor"]
        bundle.provenance[ref] = {"computed_from": [left["evidence_ref"], right["evidence_ref"]]}
        bundle.facts.append(
            {
                "evidence_ref": ref,
                "evidence_refs": [ref, left["evidence_ref"], right["evidence_ref"]],
                "role": "difference",
                "statement": (
                    f"Diferencia proveedor menos ledger: {diff} unidades menores de "
                    f"{left['currency']} ({right['amount_minor']} - {left['amount_minor']})."
                ),
            }
        )
    return bundle


@dataclass
class Verified:
    claims: list[Claim]
    issues: list[str]
    critical: bool
    next_step: str
    contradictions: list[str]
    missing_evidence: list[str]
    summary: str


def verify(draft: Any, bundle: Bundle) -> Verified:
    if not isinstance(draft, dict):
        return Verified([], ["malformed_output: draft is not a JSON object"], True,
                        "HUMAN_REVIEW", [], [], "")  # fmt: skip
    errors = list(Draft202012Validator(DRAFT_SCHEMA).iter_errors(draft))
    if errors:
        return Verified([], [f"malformed_output: {errors[0].message[:160]}"], True,
                        "HUMAN_REVIEW", [], [], "")  # fmt: skip
    issues: list[str] = []
    critical = False
    kept: list[Claim] = []
    for raw in draft["claims"]:
        claim = Claim(
            claim_id=raw["claim_id"],
            kind=raw["kind"],
            statement=raw["statement"],
            evidence_refs=tuple(raw["evidence_refs"]),
            limitations=raw["limitations"],
            needed_evidence=raw.get("needed_evidence"),
        )
        where = f"claim {claim.claim_id}"
        if claim.kind not in CLAIM_KINDS:
            issues.append(f"{where}: kind {claim.kind!r} not allowed")
            critical = True
            continue
        unknown = [r for r in claim.evidence_refs if r not in bundle.refs]
        if not claim.evidence_refs or unknown:
            issues.append(f"{where}: unresolvable citation {unknown or '(none)'}")
            critical = True
            continue
        if claim.kind == "FACT":
            if not any(r.startswith(RECORD_PREFIXES) for r in claim.evidence_refs):
                issues.append(f"{where}: FACT backed only by documents (document ≠ event)")
                critical = True
                continue
            numbers = set(_NUMBER.findall(claim.statement))
            if not numbers <= bundle.numbers(claim.evidence_refs):
                issues.append(f"{where}: numbers {sorted(numbers)} not in cited records")
                critical = True
                continue
        if claim.kind == "HYPOTHESIS" and not claim.needed_evidence:
            issues.append(f"{where}: hypothesis without the evidence needed to confirm it")
        kept.append(claim)
    next_step = draft["recommended_next_step"]
    if next_step not in NEXT_STEPS:
        issues.append(f"next step {next_step!r} is not an allowed action; replaced by HUMAN_REVIEW")
        critical = True
        next_step = "HUMAN_REVIEW"
    return Verified(
        kept,
        issues,
        critical,
        next_step,
        list(draft["contradictions"]),
        list(draft["missing_evidence"]),
        draft["summary"],
    )
