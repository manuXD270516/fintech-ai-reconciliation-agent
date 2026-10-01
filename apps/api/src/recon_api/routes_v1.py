"""Versioned business API (M2): artifact reception, batches and reconciliation runs.

Tenant always comes from the verified token, never from the request body.
Synchronous handlers run in the threadpool; durable work goes through the outbox.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import Engine

from recon_api.auth import READ_ROLES, Principal, Role, require
from recon_domain.approval import Action, Decision
from recon_domain.batch import ReconciliationBatch
from recon_domain.ingestion import ArtifactError
from recon_domain.observation import DomainError, SourceKind
from recon_store.artifacts import ArtifactService, IdempotencyConflictError
from recon_store.cases import OPERATIONAL_EFFECT, CaseError, CaseService
from recon_store.investigations import InvestigationRepository
from recon_store.reconciliation import ConflictError, NotFoundError, ReconciliationService

MAX_ARTIFACT_CHARS = 2_000_000
Ident = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
SourceName = Literal["internal_ledger", "provider_report"]
CaseStatusName = Literal[
    "OPEN", "HUMAN_REVIEW", "APPROVED", "REJECTED", "NEEDS_INFORMATION", "CLOSED"
]

router = APIRouter(prefix="/v1")


def _engine(request: Request) -> Engine:
    engine: Engine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(503, detail="storage is not configured")
    return engine


def _corr(request: Request) -> str:
    return str(request.state.request_id)


class ArtifactIn(BaseModel):
    source: SourceName
    provider_id: Ident
    idempotency_key: Ident
    content: str = Field(min_length=1, max_length=MAX_ARTIFACT_CHARS)


class RejectionOut(BaseModel):
    row_number: int
    code: str
    message: str


class ReceiptOut(BaseModel):
    artifact_id: int
    replayed: bool
    content_hash: str
    row_count: int
    accepted: int
    duplicates: int
    conflicts: int
    rejected: int
    rejections: list[RejectionOut]


class BatchIn(BaseModel):
    batch_id: Ident
    provider_id: Ident
    merchant_account: Ident
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    window_start: AwareDatetime
    window_end: AwareDatetime
    business_timezone: str = Field(min_length=1, max_length=64)
    cutoff_at: AwareDatetime
    left_source: SourceName = "internal_ledger"
    right_source: SourceName = "provider_report"


class BatchOut(BatchIn):
    left_complete: bool
    right_complete: bool
    version: int


class RunAccepted(BaseModel):
    run_id: uuid.UUID
    run_number: int
    status: Literal["requested"]


class RunOut(BaseModel):
    run_id: uuid.UUID
    batch_id: str
    run_number: int
    status: str
    ruleset_version: str
    snapshot_hash: str | None
    observation_count: int | None
    requested_by: str
    requested_at: datetime
    completed_at: datetime | None
    counts: dict[str, int]


class ResultOut(BaseModel):
    ordinal: int
    payment_ref: str
    operation_type: str
    match_status: str
    rule: str
    discrepancy_types: list[str]
    left_ids: list[int]
    right_ids: list[int]
    amount_difference_minor: int | None
    score: float | None
    alternatives: list[int]
    explanation: str


class ResultPage(BaseModel):
    items: list[ResultOut]
    next_after: int | None


def _batch_out(view: Any) -> BatchOut:
    b = view.batch
    return BatchOut(
        batch_id=b.batch_id,
        provider_id=b.provider_id,
        merchant_account=b.merchant_account,
        currency=b.currency,
        window_start=b.window_start,
        window_end=b.window_end,
        business_timezone=b.business_timezone,
        cutoff_at=b.cutoff_at,
        left_source=b.source_pair[0].value,
        right_source=b.source_pair[1].value,
        left_complete=view.left_complete,
        right_complete=view.right_complete,
        version=view.version,
    )


@router.post("/artifacts", response_model=ReceiptOut, status_code=201, tags=["ingestion"])
def post_artifact(
    body: ArtifactIn,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require(Role.INTEGRATION))],
) -> ReceiptOut:
    service = ArtifactService(_engine(request))
    try:
        receipt = service.ingest(
            tenant_id=principal.tenant_id,
            source=SourceKind(body.source),
            provider_id=body.provider_id,
            idempotency_key=body.idempotency_key,
            content=body.content,
            actor=principal.subject,
            correlation_id=_corr(request),
            now=datetime.now(UTC),
        )
    except ArtifactError as exc:
        raise HTTPException(422, detail=str(exc)) from None
    except IdempotencyConflictError:
        raise HTTPException(409, detail="idempotency key reused with different content") from None
    if receipt.replayed:
        response.status_code = 200
    return ReceiptOut(
        artifact_id=receipt.artifact_id,
        replayed=receipt.replayed,
        content_hash=receipt.content_hash,
        row_count=receipt.row_count,
        accepted=receipt.accepted,
        duplicates=receipt.duplicates,
        conflicts=receipt.conflicts,
        rejected=receipt.rejected,
        rejections=[
            RejectionOut(row_number=n, code=c, message=m) for n, c, m in receipt.rejections
        ],
    )


@router.post("/batches", response_model=BatchOut, status_code=201, tags=["reconciliation"])
def post_batch(
    body: BatchIn,
    request: Request,
    principal: Annotated[Principal, Depends(require(Role.ANALYST))],
) -> BatchOut:
    try:
        batch = ReconciliationBatch(
            tenant_id=principal.tenant_id,
            batch_id=body.batch_id,
            provider_id=body.provider_id,
            merchant_account=body.merchant_account,
            currency=body.currency,
            window_start=body.window_start.astimezone(UTC),
            window_end=body.window_end.astimezone(UTC),
            business_timezone=body.business_timezone,
            source_pair=(SourceKind(body.left_source), SourceKind(body.right_source)),
            cutoff_at=body.cutoff_at.astimezone(UTC),
        )
    except (DomainError, ValueError) as exc:
        raise HTTPException(422, detail=str(exc)) from None
    service = ReconciliationService(_engine(request))
    try:
        service.create_batch(batch, actor=principal.subject, correlation_id=_corr(request))
    except ConflictError:
        raise HTTPException(409, detail="batch already exists") from None
    return _batch_out(service.get_batch(principal.tenant_id, body.batch_id))


@router.get("/batches/{batch_id}", response_model=BatchOut, tags=["reconciliation"])
def get_batch(
    batch_id: Ident,
    request: Request,
    principal: Annotated[Principal, Depends(require(*READ_ROLES))],
) -> BatchOut:
    try:
        return _batch_out(
            ReconciliationService(_engine(request)).get_batch(principal.tenant_id, batch_id)
        )
    except NotFoundError:
        raise HTTPException(404, detail="batch not found") from None


@router.post(
    "/batches/{batch_id}/sources/{source}/complete", response_model=BatchOut, tags=["ingestion"]
)
def complete_source(
    batch_id: Ident,
    source: SourceName,
    request: Request,
    principal: Annotated[Principal, Depends(require(Role.INTEGRATION))],
) -> BatchOut:
    service = ReconciliationService(_engine(request))
    try:
        view = service.mark_complete(
            principal.tenant_id,
            batch_id,
            SourceKind(source),
            actor=principal.subject,
            correlation_id=_corr(request),
        )
    except NotFoundError:
        raise HTTPException(404, detail="batch not found") from None
    except ConflictError as exc:
        raise HTTPException(409, detail=str(exc)) from None
    return _batch_out(view)


@router.post(
    "/batches/{batch_id}/runs", response_model=RunAccepted, status_code=202, tags=["reconciliation"]
)
def post_run(
    batch_id: Ident,
    request: Request,
    principal: Annotated[Principal, Depends(require(Role.ANALYST))],
) -> RunAccepted:
    try:
        run_id, number = ReconciliationService(_engine(request)).request_run(
            principal.tenant_id, batch_id, actor=principal.subject, correlation_id=_corr(request)
        )
    except NotFoundError:
        raise HTTPException(404, detail="batch not found") from None
    return RunAccepted(run_id=run_id, run_number=number, status="requested")


@router.get("/runs/{run_id}", response_model=RunOut, tags=["reconciliation"])
def get_run(
    run_id: uuid.UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require(*READ_ROLES))],
) -> RunOut:
    service = ReconciliationService(_engine(request))
    try:
        row = service.get_run(principal.tenant_id, run_id)
    except NotFoundError:
        raise HTTPException(404, detail="run not found") from None
    return RunOut(
        run_id=row["id"],
        batch_id=row["batch_id"],
        run_number=row["run_number"],
        status=row["status"],
        ruleset_version=row["ruleset_version"],
        snapshot_hash=row["snapshot_hash"],
        observation_count=row["observation_count"],
        requested_by=row["requested_by"],
        requested_at=row["requested_at"],
        completed_at=row["completed_at"],
        counts=service.status_counts(run_id),
    )


@router.get("/runs/{run_id}/results", response_model=ResultPage, tags=["reconciliation"])
def get_results(
    run_id: uuid.UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require(*READ_ROLES))],
    match_status: Literal["EXACT", "PROBABLE", "UNMATCHED", "NOT_EVALUATED"] | None = None,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ResultPage:
    try:
        rows = ReconciliationService(_engine(request)).list_results(
            principal.tenant_id, run_id, match_status=match_status, after=after, limit=limit
        )
    except NotFoundError:
        raise HTTPException(404, detail="run not found") from None
    items = [
        ResultOut(
            ordinal=r["ordinal"],
            payment_ref=r["payment_ref"],
            operation_type=r["operation_type"],
            match_status=r["match_status"],
            rule=r["rule"],
            discrepancy_types=list(r["discrepancy_types"]),
            left_ids=list(r["left_ids"]),
            right_ids=list(r["right_ids"]),
            amount_difference_minor=r["amount_difference_minor"],
            score=None if r["score"] is None else float(r["score"]),
            alternatives=list(r["alternatives"]),
            explanation=r["explanation"],
        )
        for r in rows
    ]
    return ResultPage(items=items, next_after=items[-1].ordinal if len(items) == limit else None)


# --- M5: bounded investigations (drafts without operational effect) ---------------------


class InvestigationAccepted(BaseModel):
    investigation_id: uuid.UUID
    created: bool
    status: Literal["requested", "existing"]


class InvestigationOut(BaseModel):
    investigation_id: uuid.UUID
    case_ref: str
    case_version: int
    state: str
    requested_by: str
    created_at: datetime
    updated_at: datetime
    record: dict[str, Any]


@router.post(
    "/runs/{run_id}/results/{ordinal}/investigations",
    response_model=InvestigationAccepted,
    status_code=202,
    tags=["investigation"],
)
def post_investigation(
    run_id: uuid.UUID,
    ordinal: Annotated[int, Path(ge=1)],
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require(Role.ANALYST))],
) -> InvestigationAccepted:
    """Request a read-only investigation; repeating it without new evidence is idempotent."""
    if not getattr(request.app.state, "ai_enabled", True):
        # Kill switch (APP_AI_ENABLED=false): no new AI work; reconciliation, cases and human
        # decisions keep working on the deterministic path.
        raise HTTPException(503, detail={"code": "ai_disabled"})
    repo = InvestigationRepository(_engine(request))
    try:
        investigation_id, created = repo.request(
            principal.tenant_id, run_id, ordinal, actor=principal.subject,
            correlation_id=_corr(request),
        )  # fmt: skip
    except LookupError:
        raise HTTPException(404, detail="result not found") from None
    if not created:
        response.status_code = 200
    return InvestigationAccepted(
        investigation_id=uuid.UUID(investigation_id),
        created=created,
        status="requested" if created else "existing",
    )


@router.get(
    "/investigations/{investigation_id}", response_model=InvestigationOut, tags=["investigation"]
)
def get_investigation(
    investigation_id: uuid.UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require(*READ_ROLES))],
) -> InvestigationOut:
    row = InvestigationRepository(_engine(request)).get(principal.tenant_id, investigation_id)
    if row is None:
        raise HTTPException(404, detail="investigation not found")
    return _investigation_out(row)


def _investigation_out(row: dict[str, Any]) -> InvestigationOut:
    return InvestigationOut(
        investigation_id=row["id"],
        case_ref=row["case_ref"],
        case_version=row["case_version"],
        state=row["state"],
        requested_by=row["requested_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        record=dict(row["record"]),
    )


# --- M6: cases, recommendations and human decisions ---------------------------------------

STATUS_BY_CODE = {
    "not_found": 404,
    "role_not_allowed": 403,
    "segregation_of_duties": 403,
    "reason_required": 422,
}


def _case_error(exc: CaseError) -> HTTPException:
    detail = {"code": exc.code, "message": exc.message}
    return HTTPException(STATUS_BY_CODE.get(exc.code, 409), detail=detail)


class CaseOpened(BaseModel):
    case_id: uuid.UUID
    created: bool


class RecommendationIn(BaseModel):
    action: Action
    rationale: str = Field(min_length=10, max_length=2000)
    expected_version: int = Field(ge=1)
    investigation_id: uuid.UUID | None = None


class RecommendationCreated(BaseModel):
    recommendation_id: uuid.UUID
    status: Literal["PENDING"]


class DecisionIn(BaseModel):
    recommendation_id: uuid.UUID
    decision: Decision
    reason: str = Field(min_length=10, max_length=2000)
    expected_version: int = Field(ge=1)
    idempotency_key: Ident


class DecisionOut(BaseModel):
    decision_id: uuid.UUID
    decision: str
    approved_version: int
    replayed: bool
    operational_effect: str


class CloseIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
    expected_version: int = Field(ge=1)


@router.post(
    "/runs/{run_id}/results/{ordinal}/cases",
    response_model=CaseOpened,
    status_code=201,
    tags=["cases"],
)
def post_case(
    run_id: uuid.UUID,
    ordinal: Annotated[int, Path(ge=1)],
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require(Role.ANALYST))],
) -> CaseOpened:
    try:
        case_id, created = CaseService(_engine(request)).open(
            principal.tenant_id, run_id, ordinal, actor=principal.subject,
            correlation_id=_corr(request),
        )  # fmt: skip
    except CaseError as exc:
        raise _case_error(exc) from None
    if not created:
        response.status_code = 200
    return CaseOpened(case_id=case_id, created=created)


class RecommendationOut(BaseModel):
    id: uuid.UUID
    case_version: int
    proposer: str
    action: str
    rationale: str
    investigation_id: uuid.UUID | None
    review_result: str
    evidence: dict[str, Any]
    status: str
    expires_at: datetime
    created_at: datetime


class DecisionRecordOut(BaseModel):
    id: uuid.UUID
    recommendation_id: uuid.UUID
    approver: str
    decision: str
    reason: str
    case_version: int
    created_at: datetime


class CaseSummary(BaseModel):
    case_id: uuid.UUID
    case_ref: str
    run_id: uuid.UUID
    ordinal: int
    status: str
    version: int
    updated_at: datetime


class CaseOut(CaseSummary):
    opened_by: str
    closed_reason: str | None
    created_at: datetime
    run_is_latest: bool
    recommendations: list[RecommendationOut]
    decisions: list[DecisionRecordOut]


class AuditEntryOut(BaseModel):
    id: int
    occurred_at: datetime
    actor: str
    action: str
    resource_type: str
    resource_id: str
    resource_version: int | None
    outcome: str
    details: dict[str, Any]


class AuditTrailOut(BaseModel):
    case: dict[str, Any]
    rules: dict[str, Any]
    recommendations: list[RecommendationOut]
    decisions: list[DecisionRecordOut]
    investigations: list[dict[str, Any]]
    audit: list[AuditEntryOut]


def _case_summary(row: Any) -> CaseSummary:
    return CaseSummary(
        case_id=row["id"], case_ref=row["case_ref"], run_id=row["run_id"], ordinal=row["ordinal"],
        status=row["status"], version=row["version"], updated_at=row["updated_at"],
    )  # fmt: skip


@router.get("/cases", response_model=list[CaseSummary], tags=["cases"])
def list_cases(
    request: Request,
    principal: Annotated[Principal, Depends(require(*READ_ROLES))],
    status: CaseStatusName | None = None,
) -> list[CaseSummary]:
    rows = CaseService(_engine(request)).list_cases(principal.tenant_id, status)
    return [_case_summary(r) for r in rows]


@router.get("/cases/{case_id}", response_model=CaseOut, tags=["cases"])
def get_case(
    case_id: uuid.UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require(*READ_ROLES))],
) -> CaseOut:
    try:
        case = CaseService(_engine(request)).get(principal.tenant_id, case_id)
    except CaseError as exc:
        raise _case_error(exc) from None
    return CaseOut(
        **_case_summary(case).model_dump(),
        opened_by=case["opened_by"],
        closed_reason=case["closed_reason"],
        created_at=case["created_at"],
        run_is_latest=case["run_is_latest"],
        recommendations=[RecommendationOut(**r) for r in case["recommendations"]],
        decisions=[DecisionRecordOut(**d) for d in case["decisions"]],
    )


@router.post(
    "/cases/{case_id}/recommendations",
    response_model=RecommendationCreated,
    status_code=201,
    tags=["cases"],
)
def post_recommendation(
    case_id: uuid.UUID,
    body: RecommendationIn,
    request: Request,
    principal: Annotated[Principal, Depends(require(Role.ANALYST))],
) -> RecommendationCreated:
    """An analyst proposes; adopting an investigation draft requires a SUPPORTED review."""
    try:
        rec_id = CaseService(_engine(request)).propose(
            principal.tenant_id, case_id, actor=principal.subject, action=body.action,
            rationale=body.rationale, expected_version=body.expected_version,
            investigation_id=body.investigation_id, correlation_id=_corr(request),
            now=datetime.now(UTC),
        )  # fmt: skip
    except CaseError as exc:
        raise _case_error(exc) from None
    return RecommendationCreated(recommendation_id=rec_id, status="PENDING")


@router.post(
    "/cases/{case_id}/decisions", response_model=DecisionOut, status_code=201, tags=["cases"]
)
def post_decision(
    case_id: uuid.UUID,
    body: DecisionIn,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require(*READ_ROLES))],
) -> DecisionOut:
    """A human supervisor decides on the current version. Nothing is executed.

    Any authenticated reader reaches the policy so that refused attempts (wrong role,
    self-approval, stale version...) are audited; only supervisors can succeed.
    """
    try:
        row, replayed = CaseService(_engine(request)).decide(
            principal.tenant_id, case_id, actor=principal.subject,
            roles=frozenset(r.value for r in principal.roles),
            recommendation_id=body.recommendation_id, decision=body.decision,
            reason=body.reason, expected_version=body.expected_version,
            idempotency_key=body.idempotency_key, correlation_id=_corr(request),
            now=datetime.now(UTC),
        )  # fmt: skip
    except CaseError as exc:
        raise _case_error(exc) from None
    if replayed:
        response.status_code = 200
    return DecisionOut(
        decision_id=row["id"],
        decision=row["decision"],
        approved_version=row["case_version"],
        replayed=replayed,
        operational_effect=OPERATIONAL_EFFECT,
    )


@router.post("/cases/{case_id}/close", tags=["cases"])
def post_close(
    case_id: uuid.UUID,
    body: CloseIn,
    request: Request,
    principal: Annotated[Principal, Depends(require(Role.SUPERVISOR))],
) -> dict[str, Any]:
    try:
        version = CaseService(_engine(request)).close(
            principal.tenant_id, case_id, actor=principal.subject,
            roles=frozenset(r.value for r in principal.roles), reason=body.reason,
            expected_version=body.expected_version, correlation_id=_corr(request),
        )  # fmt: skip
    except CaseError as exc:
        raise _case_error(exc) from None
    return {"case_id": str(case_id), "status": "CLOSED", "version": version}


@router.get("/cases/{case_id}/audit", response_model=AuditTrailOut, tags=["cases"])
def get_case_audit(
    case_id: uuid.UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require(Role.AUDITOR, Role.SUPERVISOR))],
) -> AuditTrailOut:
    try:
        trail = CaseService(_engine(request)).audit_trail(
            principal.tenant_id, case_id, actor=principal.subject, correlation_id=_corr(request)
        )
    except CaseError as exc:
        raise _case_error(exc) from None
    return AuditTrailOut(**trail)


class BatchSummary(BaseModel):
    batch_id: str
    provider_id: str
    merchant_account: str
    currency: str
    window_start: datetime
    window_end: datetime
    cutoff_at: datetime
    left_complete: bool
    right_complete: bool
    version: int


class RunSummary(BaseModel):
    run_id: uuid.UUID
    run_number: int
    status: str
    ruleset_version: str
    snapshot_hash: str | None
    observation_count: int | None
    requested_at: datetime
    completed_at: datetime | None


@router.get("/batches", response_model=list[BatchSummary], tags=["reconciliation"])
def list_batches(
    request: Request,
    principal: Annotated[Principal, Depends(require(*READ_ROLES))],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[BatchSummary]:
    rows = ReconciliationService(_engine(request)).list_batches(principal.tenant_id, limit)
    return [BatchSummary(**{k: r[k] for k in BatchSummary.model_fields}) for r in rows]


@router.get("/batches/{batch_id}/runs", response_model=list[RunSummary], tags=["reconciliation"])
def list_runs(
    batch_id: Ident,
    request: Request,
    principal: Annotated[Principal, Depends(require(*READ_ROLES))],
) -> list[RunSummary]:
    try:
        rows = ReconciliationService(_engine(request)).list_runs(principal.tenant_id, batch_id)
    except NotFoundError:
        raise HTTPException(404, detail="batch not found") from None
    return [
        RunSummary(run_id=r["id"], **{k: r[k] for k in RunSummary.model_fields if k != "run_id"})
        for r in rows
    ]
