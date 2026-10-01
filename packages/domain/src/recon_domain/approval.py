"""Human approval policy (docs/04 Human-in-the-loop). Pure: no I/O, no clock reads.

Approving records a human decision on a case version; it never executes money movement.
The store applies this policy under a row lock so concurrent decisions serialize.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

RECOMMENDATION_TTL = timedelta(hours=72)
MIN_REASON_CHARS = 10


class CaseStatus(StrEnum):
    OPEN = "OPEN"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    CLOSED = "CLOSED"


class Action(StrEnum):
    """What a recommendation proposes to a person. None of them moves money."""

    ACCEPT_PROBABLE_MATCH = "ACCEPT_PROBABLE_MATCH"
    CLOSE_AS_EXPLAINED = "CLOSE_AS_EXPLAINED"
    REQUEST_PROVIDER_INFO = "REQUEST_PROVIDER_INFO"
    REQUEST_ADJUSTMENT_REVIEW = "REQUEST_ADJUSTMENT_REVIEW"


class Decision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"


class Refusal(StrEnum):
    ROLE = "role_not_allowed"
    SELF_APPROVAL = "segregation_of_duties"
    VERSION_CONFLICT = "version_conflict"
    NOT_PENDING = "recommendation_not_pending"
    EXPIRED = "recommendation_expired"
    OBSOLETE = "recommendation_obsolete"
    REASON = "reason_required"
    STATUS = "case_status_not_allowed"


CONFLICTS = {
    Refusal.VERSION_CONFLICT,
    Refusal.NOT_PENDING,
    Refusal.EXPIRED,
    Refusal.OBSOLETE,
    Refusal.STATUS,
}
TRANSITIONS = {
    Decision.APPROVE: CaseStatus.APPROVED,
    Decision.REJECT: CaseStatus.REJECTED,
    Decision.NEEDS_INFORMATION: CaseStatus.NEEDS_INFORMATION,
}
PROPOSABLE = {CaseStatus.OPEN, CaseStatus.REJECTED, CaseStatus.NEEDS_INFORMATION}
CLOSABLE = {CaseStatus.APPROVED, CaseStatus.REJECTED}


@dataclass(frozen=True, slots=True)
class CaseView:
    version: int
    status: CaseStatus
    run_is_latest: bool


@dataclass(frozen=True, slots=True)
class RecommendationView:
    proposer: str
    investigation_requester: str | None
    status: str
    case_version: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class DecisionAttempt:
    approver: str
    roles: frozenset[str]
    decision: Decision
    reason: str
    expected_version: int
    now: datetime


def check_proposal(case: CaseView, expected_version: int, rationale: str) -> Refusal | None:
    if expected_version != case.version:
        return Refusal.VERSION_CONFLICT
    if case.status not in PROPOSABLE:
        return Refusal.STATUS
    if len(rationale.strip()) < MIN_REASON_CHARS:
        return Refusal.REASON
    return None


def check_decision(  # noqa: PLR0911 - an ordered rule table
    case: CaseView, rec: RecommendationView, attempt: DecisionAttempt
) -> Refusal | None:
    """First failing rule wins; identity rules come before state rules."""
    if "supervisor" not in attempt.roles:
        return Refusal.ROLE
    if attempt.approver in {rec.proposer, rec.investigation_requester}:
        return Refusal.SELF_APPROVAL
    if len(attempt.reason.strip()) < MIN_REASON_CHARS:
        return Refusal.REASON
    if attempt.expected_version != case.version or rec.case_version != case.version:
        return Refusal.VERSION_CONFLICT
    if case.status is not CaseStatus.HUMAN_REVIEW:
        return Refusal.STATUS
    if rec.status != "PENDING":
        return Refusal.NOT_PENDING
    if not case.run_is_latest:
        return Refusal.OBSOLETE
    if attempt.now >= rec.expires_at:
        return Refusal.EXPIRED
    return None


def check_close(
    case: CaseView, expected_version: int, reason: str, roles: frozenset[str]
) -> Refusal | None:
    if "supervisor" not in roles:
        return Refusal.ROLE
    if len(reason.strip()) < MIN_REASON_CHARS:
        return Refusal.REASON
    if expected_version != case.version:
        return Refusal.VERSION_CONFLICT
    if case.status not in CLOSABLE:
        return Refusal.STATUS
    return None
