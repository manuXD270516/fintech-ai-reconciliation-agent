"""Versioned business API (M2): artifact reception, batches and reconciliation runs.

Tenant always comes from the verified token, never from the request body.
Synchronous handlers run in the threadpool; durable work goes through the outbox.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import Engine

from recon_api.auth import READ_ROLES, Principal, Role, require
from recon_domain.batch import ReconciliationBatch
from recon_domain.ingestion import ArtifactError
from recon_domain.observation import DomainError, SourceKind
from recon_store.artifacts import ArtifactService, IdempotencyConflictError
from recon_store.reconciliation import ConflictError, NotFoundError, ReconciliationService

MAX_ARTIFACT_CHARS = 2_000_000
Ident = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
SourceName = Literal["internal_ledger", "provider_report"]

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
