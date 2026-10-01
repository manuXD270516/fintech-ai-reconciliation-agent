"""OpenTelemetry tracing shared by the API, worker, investigator and MCP server.

Off by default: without `OTEL_EXPORTER_OTLP_ENDPOINT` the global tracer stays the
OpenTelemetry API no-op, spans are non-recording and no trace context is written to the
outbox. `configure()` installs the SDK with an OTLP/HTTP exporter only when the endpoint
is set and `RECON_TELEMETRY` is not `off`.

Trace context crosses process boundaries as W3C `traceparent`:
HTTP request -> outbox row (`trace_context`) -> NATS header -> consumer span, and the MCP
SDK carries it in `_meta` to `fintech-mcp-server`. Span attributes never include tenant,
subject, amounts or free text; request IDs and opaque resource IDs are allowed.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from opentelemetry import propagate, trace
from opentelemetry.context import Context

TRACEPARENT = "traceparent"
_configured: list[str] = []


def enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get("OTEL_EXPORTER_OTLP_ENDPOINT")) and env.get("RECON_TELEMETRY") != "off"


def configure(service_name: str, environ: Mapping[str, str] | None = None) -> bool:
    """Install the SDK tracer provider once per process; returns whether tracing is on."""
    if _configured:
        return True
    if not enabled(environ):
        return False
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name, "service.namespace": "recon"})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured.append(service_name)
    return True


def shutdown() -> None:
    provider = trace.get_tracer_provider()
    stop = getattr(provider, "shutdown", None)
    if callable(stop):
        stop()


def tracer() -> trace.Tracer:
    return trace.get_tracer("recon")


def current_traceparent() -> str | None:
    """W3C traceparent of the active span, or None when nothing is being recorded."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    value = carrier.get(TRACEPARENT)
    return value if value and len(value) <= 128 else None


def context_from(traceparent: str | None) -> Context | None:
    """Parent context from a stored/received traceparent; None keeps ambient parenting."""
    if not traceparent:
        return None
    ctx = propagate.extract({TRACEPARENT: traceparent})
    if not trace.get_current_span(ctx).get_span_context().is_valid:
        return None
    return ctx


def headers_with_trace(headers: dict[str, str]) -> dict[str, str]:
    value = current_traceparent()
    return headers | {TRACEPARENT: value} if value else headers
