"""Reviewer (docs/04): deterministic checks first, then an isolated model review.

The model reviewer receives only the case snapshot, the record facts and the draft claims
with their resolved citations: no planner reasoning, no previous model messages. The final
result is the most conservative of both. A review never approves anything: it only states
whether the draft is SUPPORTED, NEEDS_MORE_EVIDENCE or REJECTED, with cited objections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from recon_agents.models import CaseSnapshot

RESULTS = ("SUPPORTED", "NEEDS_MORE_EVIDENCE", "REJECTED")
SEVERITY = {result: rank for rank, result in enumerate(RESULTS)}
REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["result", "objections"],
    "properties": {
        "result": {"enum": list(RESULTS)},
        "objections": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["objection", "evidence_refs"],
                "properties": {
                    "objection": {"type": "string", "maxLength": 400},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


@dataclass
class Review:
    result: str
    objections: list[dict[str, Any]] = field(default_factory=list)
    deterministic: list[str] = field(default_factory=list)
    reviewer_model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "objections": self.objections,
            "deterministic_findings": self.deterministic,
            "reviewer_model": self.reviewer_model,
            "is_human_approval": False,
        }


def deterministic_review(case: CaseSnapshot, draft: dict[str, Any], issues: list[str]) -> Review:
    findings: list[str] = list(issues)
    facts = draft.get("facts", [])
    refs = {r for f in facts for r in f["evidence_refs"]}
    if "AMOUNT_MISMATCH" in case.discrepancy_types and "calc:difference" not in refs:
        findings.append("required element missing: computed amount difference as FACT")
    sides = {r.split("@")[0] for r in refs if r.startswith("tx:")}
    if len(sides) < min(2, len(case.left_transaction_ids) + len(case.right_transaction_ids)):
        findings.append("required element missing: both sides of the result as FACTs")
    for hypothesis in draft.get("hypotheses", []):
        if not hypothesis.get("needed_evidence"):
            findings.append(f"hypothesis {hypothesis['claim_id']} lacks the evidence to confirm it")
    if draft.get("contradictions"):
        return Review("REJECTED", deterministic=[*findings, "material contradiction reported"])
    return Review("NEEDS_MORE_EVIDENCE" if findings else "SUPPORTED", deterministic=findings)


def review_context(case: CaseSnapshot, draft: dict[str, Any]) -> dict[str, Any]:
    """Isolated reviewer input: snapshot, facts, claims and citations only."""
    return {
        "case": case.as_dict(),
        "claims": {k: draft.get(k, []) for k in ("facts", "inferences", "hypotheses")},
        "citations": draft.get("citations", []),
        "missing_evidence": draft.get("missing_evidence", []),
        "verification_issues": [],
        "instructions": "Evalúa si cada afirmación está respaldada por sus citas. No apruebes "
        "acciones; devuelve SUPPORTED, NEEDS_MORE_EVIDENCE o REJECTED con objeciones citadas.",
    }


def combine(deterministic: Review, model: dict[str, Any] | None, model_name: str) -> Review:
    if model is None:
        findings = [*deterministic.deterministic, "model review unavailable or malformed"]
        worst = max(deterministic.result, "NEEDS_MORE_EVIDENCE", key=SEVERITY.__getitem__)
        return Review(worst, deterministic.objections, findings, model_name)
    worst = max(deterministic.result, model["result"], key=SEVERITY.__getitem__)
    return Review(worst, list(model["objections"]), deterministic.deterministic, model_name)
