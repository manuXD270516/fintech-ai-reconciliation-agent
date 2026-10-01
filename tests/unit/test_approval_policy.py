"""M6 T03: pure human-approval policy (segregation of duties, versions, expiry, obsolescence)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon_domain.approval import (
    CaseStatus,
    CaseView,
    Decision,
    DecisionAttempt,
    RecommendationView,
    Refusal,
    check_close,
    check_decision,
    check_proposal,
)

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
CASE = CaseView(version=2, status=CaseStatus.HUMAN_REVIEW, run_is_latest=True)
REC = RecommendationView("ana", "ana", "PENDING", 2, NOW + timedelta(hours=1))
OK = DecisionAttempt("sofia", frozenset({"supervisor"}), Decision.APPROVE,
                     "diferencia confirmada por el proveedor", 2, NOW)  # fmt: skip


def test_valid_decision_passes() -> None:
    assert check_decision(CASE, REC, OK) is None


@pytest.mark.parametrize(
    ("case", "rec", "attempt", "refusal"),
    [
        (CASE, REC, replace(OK, roles=frozenset({"analyst"})), Refusal.ROLE),
        (CASE, REC, replace(OK, approver="ana"), Refusal.SELF_APPROVAL),  # HU01 proposer
        # also the analyst who requested the investigation
        (CASE, replace(REC, proposer="luis"), replace(OK, approver="ana"), Refusal.SELF_APPROVAL),
        (CASE, REC, replace(OK, reason="ok"), Refusal.REASON),
        (CASE, REC, replace(OK, expected_version=1), Refusal.VERSION_CONFLICT),  # HU02 stale
        (CASE, replace(REC, case_version=1), OK, Refusal.VERSION_CONFLICT),
        (replace(CASE, status=CaseStatus.APPROVED), REC, OK, Refusal.STATUS),
        (CASE, replace(REC, status="SUPERSEDED"), OK, Refusal.NOT_PENDING),
        (replace(CASE, run_is_latest=False), REC, OK, Refusal.OBSOLETE),  # RC10 late data
        (CASE, replace(REC, expires_at=NOW), OK, Refusal.EXPIRED),
    ],
)
def test_refusals(
    case: CaseView, rec: RecommendationView, attempt: DecisionAttempt, refusal: Refusal
) -> None:
    assert check_decision(case, rec, attempt) is refusal


@given(st.text(min_size=1, max_size=20).filter(lambda s: s.strip() != ""))
def test_nobody_approves_their_own_proposal(subject: str) -> None:
    rec = replace(REC, proposer=subject, investigation_requester=None)
    attempt = replace(OK, approver=subject, roles=frozenset({"supervisor", "analyst"}))
    assert check_decision(CASE, rec, attempt) is Refusal.SELF_APPROVAL


def test_proposal_and_close_rules() -> None:
    open_case = replace(CASE, status=CaseStatus.OPEN, version=1)
    assert check_proposal(open_case, 1, "la diferencia requiere confirmación") is None
    assert check_proposal(open_case, 2, "la diferencia requiere confirmación") is (
        Refusal.VERSION_CONFLICT
    )
    assert check_proposal(CASE, 2, "la diferencia requiere confirmación") is Refusal.STATUS
    assert check_proposal(open_case, 1, "corto") is Refusal.REASON
    approved = replace(CASE, status=CaseStatus.APPROVED, version=3)
    sup = frozenset({"supervisor"})
    assert check_close(approved, 3, "cerrado tras confirmación", sup) is None
    assert check_close(approved, 3, "cerrado tras confirmación", frozenset({"analyst"})) is (
        Refusal.ROLE
    )
    assert check_close(CASE, 2, "cerrado tras confirmación", sup) is Refusal.STATUS
