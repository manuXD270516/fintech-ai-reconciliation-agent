from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

from recon_api.config import Settings
from recon_api.middleware import RequestContextMiddleware
from recon_api.readiness import CheckStatus, ReadinessChecker


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
    settings: Settings | None = None, checker: ReadinessChecker | None = None
) -> FastAPI:
    if checker is None:
        if settings is None:
            raise ValueError("create_app needs settings or an explicit readiness checker")
        checker = ReadinessChecker.from_settings(settings)

    app = FastAPI(
        title="recon-api (M0 bootstrap)",
        version="0.0.0",
        description="Health endpoints only. No payment, reconciliation or agent operations.",
        redoc_url=None,
    )
    app.add_middleware(RequestContextMiddleware)
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
