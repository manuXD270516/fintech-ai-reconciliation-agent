from __future__ import annotations

import logging
import re
import time
import uuid

from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from recon_api.metrics import UNMATCHED_ROUTE, HttpMetrics
from recon_store import telemetry

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_MAX_LOGGED_PATH = 256

logger = logging.getLogger("recon_api.access")


def route_template(scope: Scope) -> str:
    """Matched route template (e.g. `/v1/runs/{run_id}`), never the raw path."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else UNMATCHED_ROUTE


def resolve_request_id(candidate: str | None) -> tuple[str, str]:
    if candidate is not None and _VALID_REQUEST_ID.fullmatch(candidate):
        return candidate, "client"
    return uuid.uuid4().hex, "generated"


class RequestContextMiddleware:
    """Assigns a validated request ID, echoes it and emits one access log per request.

    Query strings and bodies are never logged.
    """

    def __init__(self, app: ASGIApp, metrics: HttpMetrics | None = None) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id, source = resolve_request_id(headers.get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        span = telemetry.tracer().start_span(
            f"{scope['method']} request",
            kind=SpanKind.SERVER,
            context=telemetry.context_from(headers.get(telemetry.TRACEPARENT)),
            attributes={"http.request.method": scope["method"], "recon.request_id": request_id},
        )
        try:
            with trace.use_span(span, end_on_exit=False):
                await self.app(scope, receive, send_with_request_id)
        finally:
            route = route_template(scope)
            elapsed = time.perf_counter() - started
            span.update_name(f"{scope['method']} {route}")
            span.set_attributes({"http.route": route, "http.response.status_code": status_code})
            if status_code >= 500:
                span.set_status(StatusCode.ERROR)
            span.end()
            if self.metrics is not None:
                self.metrics.observe(scope["method"], route, status_code, elapsed)
            logger.info(
                "request",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "request_id_source": source,
                        "method": scope["method"],
                        "path": scope["path"][:_MAX_LOGGED_PATH],
                        "status": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                },
            )
