"""Deterministic routing: decide whether an investigation adds value before any model call.

Exact matches never reach a model. Waiting and confirmed-missing results are explained by
the rules themselves and go straight to people. Investigation needs an explicit reason.
"""

from __future__ import annotations

from dataclasses import dataclass

from recon_agents.models import CaseSnapshot


@dataclass(frozen=True, slots=True)
class Route:
    investigate: bool
    reason: str
    explanation: str


def route(case: CaseSnapshot) -> Route:  # noqa: PLR0911 - an explicit decision table
    types = set(case.discrepancy_types)
    if case.match_status == "EXACT":
        return Route(False, "exact_match", "rules/v1 exact match; no investigation needed")
    if "WAITING_SOURCE" in types:
        return Route(False, "waiting_source", "counterpart may still arrive; rerun after cutoff")
    if types & {"MISSING_INTERNAL", "MISSING_EXTERNAL"}:
        return Route(
            False,
            "deterministic_missing",
            "window closed and sources complete; deterministic diagnosis goes to human review",
        )
    if case.match_status == "PROBABLE" or case.rule == "weak_ambiguous":
        return Route(True, "ambiguous_candidates", "weak candidates need contextual evidence")
    if "PROCESSING_ERROR" in types:
        return Route(True, "unknown_status", "a quarantined row needs vocabulary context")
    if "DUPLICATE_CANDIDATE" in types:
        return Route(True, "duplicate_context", "possible economic duplicate needs context")
    if types & {"AMOUNT_MISMATCH", "STATUS_MISMATCH"}:
        return Route(True, "needs_context", "linked differences may have documented causes")
    return Route(False, "no_reason", "no explicit reason to investigate")
