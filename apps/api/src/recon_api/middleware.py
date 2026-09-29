from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_MAX_LOGGED_PATH = 256

logger = logging.getLogger("recon_api.access")


def resolve_request_id(candidate: str | None) -> tuple[str, str]:
    if candidate is not None and _VALID_REQUEST_ID.fullmatch(candidate):
        return candidate, "client"
    return uuid.uuid4().hex, "generated"


class RequestContextMiddleware:
    """Assigns a validated request ID, echoes it and emits one access log per request.

    Query strings and bodies are never logged.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id, source = resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
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
