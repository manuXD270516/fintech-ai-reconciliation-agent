from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal

import nats
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from nats.js.errors import NotFoundError as JsNotFoundError
from pydantic import BaseModel
from sqlalchemy import Engine

from recon_api.auth import JwtVerifier
from recon_api.config import Settings
from recon_api.metrics import CONTENT_TYPE, DlqSource, HttpMetrics, SnapshotSource, render
from recon_api.middleware import RequestContextMiddleware
from recon_api.readiness import CheckStatus, ReadinessChecker
from recon_api.routes_v1 import router as v1_router
from recon_store.engine import runtime_engine, runtime_url
from recon_store.ops import OpsSnapshot, snapshot

# Owned by recon_worker (runner/dlq); the API only reads the triage backlog.
DLQ_STREAM = "RECON_DLQ"
DLQ_TRIAGE = "dlq-triage"


class LiveResponse(BaseModel):
    status: Literal["alive"]
    request_id: str


class ReadyChecks(BaseModel):
    database: CheckStatus
    vector: CheckStatus
    messaging: CheckStatus


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    request_id: str
    checks: ReadyChecks


def _snapshot_source(engine: Engine) -> SnapshotSource:
    async def source() -> OpsSnapshot:
        return await asyncio.to_thread(snapshot, engine, datetime.now(UTC))

    return source


def _dlq_source(settings: Settings) -> DlqSource:
    async def source() -> int:
        async def _silence(_: Exception) -> None:
            return None

        nc = await nats.connect(
            servers=[settings.nats_url],
            user=settings.nats_user,
            password=settings.nats_password.get_secret_value(),
            name="recon-api-metrics",
            connect_timeout=2,
            allow_reconnect=False,
            max_reconnect_attempts=0,
            error_cb=_silence,
        )
        js = nc.jetstream(timeout=2)
        try:
            consumer = await js.consumer_info(DLQ_STREAM, DLQ_TRIAGE)
            return int(consumer.num_pending) + int(consumer.num_ack_pending)
        except JsNotFoundError:
            try:  # no triage consumer yet: every stored dead letter is unhandled
                return int((await js.stream_info(DLQ_STREAM)).state.messages)
            except JsNotFoundError:
                return 0  # the worker creates the stream on start
        finally:
            await nc.close()

    return source


def create_app(
    settings: Settings | None = None,
    checker: ReadinessChecker | None = None,
    *,
    verifier: JwtVerifier | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    if checker is None:
        if settings is None:
            raise ValueError("create_app needs settings or an explicit readiness checker")
        checker = ReadinessChecker.from_settings(settings)
    if settings is not None:
        if engine is None:
            engine = runtime_engine(
                runtime_url(
                    settings.db_host,
                    settings.db_port,
                    settings.db_name,
                    settings.db_user,
                    settings.db_password.get_secret_value(),
                )
            )
        if verifier is None and settings.auth_jwks_file.is_file():
            verifier = JwtVerifier.from_file(
                settings.auth_jwks_file, settings.auth_issuer, settings.auth_audience
            )

    app = FastAPI(
        title="recon-api",
        version="0.2.0",
        description=(
            "Health, synthetic artifact reception and deterministic reconciliation runs. "
            "No money movement and no agent operations."
        ),
        redoc_url=None,
    )
    http_metrics = HttpMetrics()
    app.add_middleware(RequestContextMiddleware, metrics=http_metrics)
    app.state.verifier = verifier
    app.state.engine = engine
    app.state.http_metrics = http_metrics
    app.include_router(v1_router)
    readiness = checker
    snapshot_source = _snapshot_source(engine) if engine is not None else None
    dlq_source = _dlq_source(settings) if settings is not None else None

    @app.get(
        "/metrics",
        response_class=PlainTextResponse,
        tags=["observability"],
        summary="Prometheus metrics (aggregated; no tenant or resource IDs)",
    )
    async def metrics() -> PlainTextResponse:
        body = await render(http_metrics, snapshot_source, dlq_source)
        return PlainTextResponse(
            body, media_type=CONTENT_TYPE, headers={"Cache-Control": "no-store"}
        )

    @app.get("/health/live", response_model=LiveResponse, tags=["health"])
    async def live(request: Request, response: Response) -> LiveResponse:
        response.headers["Cache-Control"] = "no-store"
        return LiveResponse(status="alive", request_id=request.state.request_id)

    @app.get(
        "/health/ready",
        response_model=ReadyResponse,
        responses={503: {"model": ReadyResponse}},
        tags=["health"],
    )
    async def ready(request: Request, response: Response) -> ReadyResponse:
        checks = await readiness.check()
        is_ready = all(value == "ok" for value in checks.values())
        response.status_code = 200 if is_ready else 503
        response.headers["Cache-Control"] = "no-store"
        return ReadyResponse(
            status="ready" if is_ready else "not_ready",
            request_id=request.state.request_id,
            checks=ReadyChecks(**checks),
        )

    return app
