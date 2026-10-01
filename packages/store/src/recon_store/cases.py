"""Case management and human approval (M6).

Every command verifies tenant, role and version and commits state + audit + outbox in one
transaction under a row lock on the case, so concurrent decisions serialize: exactly one
transition wins and the other gets a version conflict or an idempotent replay. Refused
attempts are audited in their own transaction. Nothing here executes money movement.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, RowMapping, func, insert, select, update

from recon_domain.approval import (
    RECOMMENDATION_TTL,
    Action,
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
from recon_store.tables import (
    audit_entries,
    cases,
    decisions,
    investigations,
    outbox,
    recommendations,
    results,
    runs,
)

APPROVAL_RECORDED = "ApprovalRecorded"
CASE_CLOSED = "CaseClosed"
OPERATIONAL_EFFECT = "none: the decision is recorded; no money movement is executed"


class CaseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _audit(
    conn: Connection,
    tenant_id: str,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    version: int | None,
    outcome: str,
    correlation_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        insert(audit_entries).values(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_version=version,
            outcome=outcome,
            correlation_id=correlation_id,
            details=details or {},
        )
    )


def _event(conn: Connection, tenant_id: str, event_type: str, case_id: str, version: int,
           correlation_id: str, payload: dict[str, Any]) -> None:  # fmt: skip
    conn.execute(
        insert(outbox).values(
            event_id=uuid.uuid4(),
            event_type=event_type,
            schema_version=1,
            tenant_id=tenant_id,
            aggregate_id=f"case/{case_id}",
            aggregate_version=version,
            correlation_id=correlation_id,
            payload=payload,
        )
    )


class CaseService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # --- reads --------------------------------------------------------------------------

    def _case(self, conn: Connection, tenant_id: str, case_id: uuid.UUID, lock: bool = False
              ) -> RowMapping:  # fmt: skip
        stmt = select(cases).where(cases.c.tenant_id == tenant_id, cases.c.id == case_id)
        row = conn.execute(stmt.with_for_update() if lock else stmt).mappings().first()
        if row is None:
            raise CaseError("not_found", "case not found")
        return row

    def _run_is_latest(self, conn: Connection, case: RowMapping) -> bool:
        run = conn.execute(select(runs).where(runs.c.id == case["run_id"])).mappings().one()
        newest: int | None = conn.execute(
            select(func.max(runs.c.run_number)).where(
                runs.c.tenant_id == run["tenant_id"],
                runs.c.batch_id == run["batch_id"],
                runs.c.status == "completed",
            )
        ).scalar_one()
        return bool(newest == run["run_number"])

    def get(self, tenant_id: str, case_id: uuid.UUID) -> dict[str, Any]:
        with self.engine.connect() as conn:
            case = dict(self._case(conn, tenant_id, case_id))
            case["recommendations"] = [
                dict(r)
                for r in conn.execute(
                    select(recommendations)
                    .where(recommendations.c.case_id == case_id)
                    .order_by(recommendations.c.created_at)
                ).mappings()
            ]
            case["decisions"] = [
                dict(d)
                for d in conn.execute(
                    select(decisions)
                    .where(decisions.c.case_id == case_id)
                    .order_by(decisions.c.created_at)
                ).mappings()
            ]
            case["run_is_latest"] = self._run_is_latest(conn, self._case(conn, tenant_id, case_id))
        return case

    # --- commands -----------------------------------------------------------------------

    def open(
        self, tenant_id: str, run_id: uuid.UUID, ordinal: int, *, actor: str, correlation_id: str
    ) -> tuple[uuid.UUID, bool]:
        case_ref = f"{run_id}#{ordinal}"
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(results.c.id)
                .join(runs, runs.c.id == results.c.run_id)
                .where(
                    runs.c.tenant_id == tenant_id,
                    results.c.run_id == run_id,
                    results.c.ordinal == ordinal,
                )
            ).first()
            if exists is None:
                raise CaseError("not_found", "result not found")
            token = f"case|{tenant_id}|{case_ref}"
            conn.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(token, 0))))
            current = conn.execute(
                select(cases.c.id).where(
                    cases.c.tenant_id == tenant_id, cases.c.case_ref == case_ref
                )
            ).scalar_one_or_none()
            if current is not None:
                return current, False
            case_id = uuid.uuid4()
            conn.execute(
                insert(cases).values(
                    id=case_id, tenant_id=tenant_id, case_ref=case_ref, run_id=run_id,
                    ordinal=ordinal, status=CaseStatus.OPEN.value, version=1, opened_by=actor,
                )
            )  # fmt: skip
            _audit(conn, tenant_id, actor, "case.open", "case", str(case_id), 1, "opened",
                   correlation_id, {"case_ref": case_ref})  # fmt: skip
        return case_id, True

    def propose(
        self,
        tenant_id: str,
        case_id: uuid.UUID,
        *,
        actor: str,
        action: Action,
        rationale: str,
        expected_version: int,
        investigation_id: uuid.UUID | None,
        correlation_id: str,
        now: datetime,
    ) -> uuid.UUID:
        with self.engine.begin() as conn:
            case = self._case(conn, tenant_id, case_id, lock=True)
            view = CaseView(case["version"], CaseStatus(case["status"]), True)
            refusal = check_proposal(view, expected_version, rationale)
            if refusal is not None:
                raise CaseError(refusal.value, f"proposal refused: {refusal.value}")
            evidence: dict[str, Any] = {"case_ref": case["case_ref"], "source": "analyst"}
            review_result, requester = "NOT_REVIEWED", None
            if investigation_id is not None:
                inv = conn.execute(
                    select(investigations).where(
                        investigations.c.tenant_id == tenant_id,
                        investigations.c.id == investigation_id,
                    )
                ).mappings().first()  # fmt: skip
                if inv is None or inv["case_ref"] != case["case_ref"]:
                    raise CaseError("not_found", "investigation not found for this case")
                draft = (inv["record"] or {}).get("draft") or {}
                review_result = (draft.get("review_result") or {}).get("result", "NOT_REVIEWED")
                if inv["state"] != "DRAFTED" or review_result != "SUPPORTED":
                    raise CaseError(
                        Refusal.STATUS.value, "only drafts reviewed as SUPPORTED can be adopted"
                    )
                requester = inv["requested_by"]
                evidence = {
                    "case_ref": case["case_ref"],
                    "source": "investigation",
                    "investigation_id": str(investigation_id),
                    "label": draft.get("label"),
                    "citations": [c["ref"] for c in draft.get("citations", [])],
                    "facts": [f["statement"] for f in draft.get("facts", [])],
                    "hypotheses": [h["statement"] for h in draft.get("hypotheses", [])],
                }
            new_version = case["version"] + 1
            conn.execute(
                update(recommendations)
                .where(recommendations.c.case_id == case_id, recommendations.c.status == "PENDING")
                .values(status="SUPERSEDED")
            )
            rec_id = uuid.uuid4()
            conn.execute(
                insert(recommendations).values(
                    id=rec_id, case_id=case_id, tenant_id=tenant_id, case_version=new_version,
                    proposer=actor, action=action.value, rationale=rationale.strip(),
                    investigation_id=investigation_id, investigation_requester=requester,
                    review_result=review_result, evidence=evidence, status="PENDING",
                    expires_at=now + RECOMMENDATION_TTL,
                )
            )  # fmt: skip
            conn.execute(
                update(cases)
                .where(cases.c.id == case_id)
                .values(status=CaseStatus.HUMAN_REVIEW.value, version=new_version,
                        updated_at=func.now())
            )  # fmt: skip
            _audit(conn, tenant_id, actor, "recommendation.create", "recommendation",
                   str(rec_id), new_version, "pending", correlation_id,
                   {"case_id": str(case_id), "action": action.value,
                    "review_result": review_result})  # fmt: skip
        return rec_id

    def decide(
        self,
        tenant_id: str,
        case_id: uuid.UUID,
        *,
        actor: str,
        roles: frozenset[str],
        recommendation_id: uuid.UUID,
        decision: Decision,
        reason: str,
        expected_version: int,
        idempotency_key: str,
        correlation_id: str,
        now: datetime,
    ) -> tuple[dict[str, Any], bool]:
        refusal: Refusal | None = None
        with self.engine.begin() as conn:
            case = self._case(conn, tenant_id, case_id, lock=True)
            prior = conn.execute(
                select(decisions).where(
                    decisions.c.tenant_id == tenant_id,
                    decisions.c.idempotency_key == idempotency_key,
                )
            ).mappings().first()  # fmt: skip
            if prior is not None:
                same = (prior["case_id"], prior["recommendation_id"], prior["decision"],
                        prior["reason"]) == (case_id, recommendation_id, decision.value,
                                             reason.strip())  # fmt: skip
                if not same:
                    raise CaseError("idempotency_conflict", "idempotency key reused differently")
                return dict(prior), True
            rec = conn.execute(
                select(recommendations).where(
                    recommendations.c.id == recommendation_id,
                    recommendations.c.case_id == case_id,
                )
            ).mappings().first()  # fmt: skip
            if rec is None:
                raise CaseError("not_found", "recommendation not found")
            view = CaseView(
                case["version"], CaseStatus(case["status"]), self._run_is_latest(conn, case)
            )
            rec_view = RecommendationView(rec["proposer"], rec["investigation_requester"],
                                          rec["status"], rec["case_version"],
                                          rec["expires_at"])  # fmt: skip
            attempt = DecisionAttempt(actor, roles, decision, reason, expected_version, now)
            refusal = check_decision(view, rec_view, attempt)
            if refusal is None:
                decision_id = uuid.uuid4()
                new_version = case["version"] + 1
                row = {
                    "id": decision_id, "case_id": case_id, "recommendation_id": recommendation_id,
                    "tenant_id": tenant_id, "approver": actor, "role": "supervisor",
                    "decision": decision.value, "reason": reason.strip(),
                    "case_version": case["version"], "idempotency_key": idempotency_key,
                }  # fmt: skip
                conn.execute(insert(decisions).values(**row))
                status = {Decision.APPROVE: "APPROVED", Decision.REJECT: "REJECTED",
                          Decision.NEEDS_INFORMATION: "NEEDS_INFORMATION"}[decision]  # fmt: skip
                conn.execute(
                    update(recommendations)
                    .where(recommendations.c.id == recommendation_id)
                    .values(status=status)
                )
                conn.execute(
                    update(cases)
                    .where(cases.c.id == case_id)
                    .values(status=status, version=new_version, updated_at=func.now())
                )
                details = {"recommendation_id": str(recommendation_id), "decision": decision.value,
                           "approved_version": case["version"], "action": rec["action"],
                           "operational_effect": OPERATIONAL_EFFECT}  # fmt: skip
                _audit(conn, tenant_id, actor, "decision.record", "decision", str(decision_id),
                       new_version, decision.value.lower(), correlation_id, details)  # fmt: skip
                _event(conn, tenant_id, APPROVAL_RECORDED, str(case_id), new_version,
                       correlation_id, details | {"case_id": str(case_id)})  # fmt: skip
                return row | {"created_at": now}, False
        with self.engine.begin() as conn:  # refused: record the attempt, keep the case intact
            if refusal is Refusal.OBSOLETE:
                conn.execute(
                    update(recommendations)
                    .where(recommendations.c.id == recommendation_id,
                           recommendations.c.status == "PENDING")
                    .values(status="OBSOLETE")
                )  # fmt: skip
            _audit(conn, tenant_id, actor, "decision.denied", "case", str(case_id),
                   expected_version, refusal.value if refusal else "denied", correlation_id,
                   {"recommendation_id": str(recommendation_id),
                    "decision": decision.value})  # fmt: skip
        assert refusal is not None  # noqa: S101 - success returned above
        raise CaseError(refusal.value, f"decision refused: {refusal.value}")

    def close(
        self,
        tenant_id: str,
        case_id: uuid.UUID,
        *,
        actor: str,
        roles: frozenset[str],
        reason: str,
        expected_version: int,
        correlation_id: str,
    ) -> int:
        with self.engine.begin() as conn:
            case = self._case(conn, tenant_id, case_id, lock=True)
            view = CaseView(case["version"], CaseStatus(case["status"]), True)
            refusal = check_close(view, expected_version, reason, roles)
            if refusal is not None:
                raise CaseError(refusal.value, f"close refused: {refusal.value}")
            new_version = int(case["version"]) + 1
            conn.execute(
                update(cases)
                .where(cases.c.id == case_id)
                .values(status=CaseStatus.CLOSED.value, version=new_version,
                        closed_reason=reason.strip()[:500], updated_at=func.now())
            )  # fmt: skip
            _audit(conn, tenant_id, actor, "case.close", "case", str(case_id), new_version,
                   "closed", correlation_id, {"reason": reason.strip()[:200]})  # fmt: skip
            _event(conn, tenant_id, CASE_CLOSED, str(case_id), new_version, correlation_id,
                   {"case_id": str(case_id)})  # fmt: skip
        return new_version

    def audit_trail(
        self, tenant_id: str, case_id: uuid.UUID, *, actor: str, correlation_id: str
    ) -> dict[str, Any]:
        """Reconstruct who decided what, on which version, with which evidence (UC08)."""
        case = self.get(tenant_id, case_id)
        with self.engine.begin() as conn:
            run = conn.execute(select(runs).where(runs.c.id == case["run_id"])).mappings().one()
            inv_ids = [r["investigation_id"] for r in case["recommendations"]
                       if r["investigation_id"]]  # fmt: skip
            invs = [
                dict(i)
                for i in conn.execute(
                    select(investigations).where(investigations.c.id.in_(inv_ids or [uuid.uuid4()]))
                ).mappings()
            ]
            resource_ids = [str(case_id), *(str(r["id"]) for r in case["recommendations"]),
                            *(str(d["id"]) for d in case["decisions"]),
                            *(str(i["id"]) for i in invs)]  # fmt: skip
            entries = [
                dict(e)
                for e in conn.execute(
                    select(audit_entries)
                    .where(audit_entries.c.tenant_id == tenant_id,
                           audit_entries.c.resource_id.in_(resource_ids))
                    .order_by(audit_entries.c.id)
                ).mappings()
            ]  # fmt: skip
            _audit(conn, tenant_id, actor, "case.audit_read", "case", str(case_id),
                   case["version"], "read", correlation_id)  # fmt: skip
        return {
            "case": {k: v for k, v in case.items() if k not in ("recommendations", "decisions")},
            "rules": {"ruleset_version": run["ruleset_version"],
                      "snapshot_hash": run["snapshot_hash"], "run_number": run["run_number"]},
            "recommendations": case["recommendations"],
            "decisions": case["decisions"],
            "investigations": [
                {"investigation_id": str(i["id"]), "state": i["state"],
                 "input_snapshot_hash": i["input_snapshot_hash"],
                 "steps": (i["record"] or {}).get("steps", []),
                 "citations": ((i["record"] or {}).get("draft") or {}).get("citations", []),
                 "review": ((i["record"] or {}).get("draft") or {}).get("review_result")}
                for i in invs
            ],
            "audit": entries,
        }  # fmt: skip
