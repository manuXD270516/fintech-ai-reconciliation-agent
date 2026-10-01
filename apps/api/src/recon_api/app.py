from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from sqlalchemy import Engine

from recon_api.auth import JwtVerifier
from recon_api.config import Settings
from recon_api.middleware import RequestContextMiddleware
from recon_api.readiness import CheckStatus, ReadinessChecker
from recon_api.routes_v1 import router as v1_router
from recon_store.engine import runtime_engine, runtime_url


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
    app.add_middleware(RequestContextMiddleware)
    app.state.verifier = verifier
    app.state.engine = engine
    app.include_router(v1_router)
    readiness = checker

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
