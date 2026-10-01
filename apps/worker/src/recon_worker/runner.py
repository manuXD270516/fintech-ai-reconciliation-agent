"""Outbox relay + JetStream consumers with inbox deduplication (at-least-once delivery).

Streams:
- RECON_EVENTS  `recon.events.<EventType>`: domain events published from the outbox.
- RECON_INGEST  `recon.ingest.<tenant>.<source>.<provider>`: synthetic source events. The
  tenant/source/provider come from the subject (the channel identity), never from the body.
- RECON_DLQ     `recon.dlq.<consumer>`: poison or exhausted messages with a reason.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from nats.aio.client import Client as NatsClient
from nats.aio.msg import Msg
from nats.js import JetStreamContext
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DeliverPolicy,
    RetentionPolicy,
    StorageType,
    StreamConfig,
)
from nats.js.errors import NotFoundError
from opentelemetry.trace import Span, SpanKind, StatusCode
from sqlalchemy import Engine

from recon_domain.ingestion import ArtifactError, rows_to_csv
from recon_domain.observation import DomainError, SourceKind, require_ident
from recon_store import telemetry
from recon_store.artifacts import ArtifactService, IdempotencyConflictError
from recon_store.ops import beat
from recon_store.outbox import mark_failed, mark_published, pending
from recon_store.reconciliation import (
    RECONCILIATION_REQUESTED,
    ReconciliationService,
    record_inbox,
)

STREAM = "RECON_EVENTS"
SUBJECT_PREFIX = "recon.events"
INGEST_STREAM = "RECON_INGEST"
INGEST_PREFIX = "recon.ingest"
DLQ_STREAM = "RECON_DLQ"
DLQ_PREFIX = "recon.dlq"
RUN_CONSUMER = "reconciliation-runner"
INGEST_CONSUMER = "observation-ingestor"
DLQ_TRIAGE = "dlq-triage"
MAX_DELIVER = 5
MAX_EVENT_BYTES = 16_384
HEARTBEAT_SECONDS = 10.0

log = logging.getLogger("recon_worker")
Handler = Callable[[Engine, dict[str, object], str], str]


class PoisonMessageError(ValueError):
    """The message can never succeed (malformed); it goes straight to the DLQ."""


def subject(event_type: str) -> str:
    return f"{SUBJECT_PREFIX}.{event_type}"


def ingest_subject(tenant_id: str, source: SourceKind, provider_id: str) -> str:
    return f"{INGEST_PREFIX}.{tenant_id}.{source.value}.{provider_id}"


async def _ensure(js: JetStreamContext, config: StreamConfig) -> None:
    try:
        await js.stream_info(str(config.name))
        await js.update_stream(config)
    except NotFoundError:
        await js.add_stream(config)


async def ensure_stream(js: JetStreamContext) -> None:
    for name, subjects in (
        (STREAM, [f"{SUBJECT_PREFIX}.>"]),
        (INGEST_STREAM, [f"{INGEST_PREFIX}.>"]),
        (DLQ_STREAM, [f"{DLQ_PREFIX}.>"]),
    ):
        await _ensure(
            js,
            StreamConfig(
                name=name,
                subjects=subjects,
                retention=RetentionPolicy.LIMITS,
                storage=StorageType.FILE,
                duplicate_window=120.0,
                max_age=7 * 24 * 3600.0,
            ),
        )
    # Operators triage dead letters through this durable consumer (recon_worker.dlq);
    # its pending count is the `recon_dead_letters_unhandled` metric.
    await js.add_consumer(
        DLQ_STREAM,
        ConsumerConfig(
            durable_name=DLQ_TRIAGE,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            ack_wait=30,
        ),
    )


async def relay_once(engine: Engine, js: JetStreamContext, limit: int = 100) -> int:
    events = await asyncio.to_thread(pending, engine, limit)
    published: list[uuid.UUID] = []
    for event in events:
        try:
            with telemetry.tracer().start_as_current_span(
                f"publish {event.event_type}",
                kind=SpanKind.PRODUCER,
                context=telemetry.context_from(event.trace_context),
                attributes={
                    "messaging.system": "nats",
                    "messaging.destination.name": subject(event.event_type),
                    "messaging.message.id": str(event.event_id),
                },
            ):
                await js.publish(
                    subject(event.event_type),
                    json.dumps(event.envelope, separators=(",", ":")).encode(),
                    headers=telemetry.headers_with_trace({"Nats-Msg-Id": str(event.event_id)}),
                    timeout=5,
                )
            published.append(event.event_id)
        except Exception as exc:
            await asyncio.to_thread(mark_failed, engine, event.event_id, type(exc).__name__)
            log.warning("outbox publish failed", extra={"event_type": event.event_type})
            break
    await asyncio.to_thread(mark_published, engine, published, datetime.now(UTC))
    return len(published)


def handle_run_requested(engine: Engine, envelope: dict[str, object], subject: str = "") -> str:
    """Execute a requested run exactly once per event (inbox + effect in one transaction)."""
    try:
        event_id = uuid.UUID(str(envelope["event_id"]))
        payload = envelope["payload"]
        if not isinstance(payload, dict):
            raise TypeError("payload must be an object")
        run_id = uuid.UUID(str(payload["run_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PoisonMessageError(f"malformed {RECONCILIATION_REQUESTED}: {exc}") from None
    service = ReconciliationService(engine)
    with engine.begin() as conn:
        if not record_inbox(conn, RUN_CONSUMER, event_id):
            return "duplicate"
        service.execute_run(conn, run_id, datetime.now(UTC), causation_id=str(event_id))
    return "processed"


def parse_ingest_subject(value: str) -> tuple[str, SourceKind, str]:
    parts = value.split(".")
    if len(parts) != 5 or ".".join(parts[:2]) != INGEST_PREFIX:
        raise PoisonMessageError("ingest subject must be recon.ingest.<tenant>.<source>.<provider>")
    try:
        tenant = require_ident("tenant_id", parts[2])
        return tenant, SourceKind(parts[3]), require_ident("provider_id", parts[4])
    except (DomainError, ValueError):
        raise PoisonMessageError("invalid tenant, source or provider in subject") from None


def handle_observation_event(engine: Engine, envelope: dict[str, object], subject: str) -> str:
    """Ingest one source event as a single-row artifact keyed by its event_id.

    The artifact idempotency key makes redelivery a no-op (`replayed`); a reused event_id
    with different content is a conflict and is not retried. Row-level problems are
    quarantined exactly like CSV rows.
    """
    tenant_id, source, provider_id = parse_ingest_subject(subject)
    event_id, record = envelope.get("event_id"), envelope.get("record")
    try:
        key = f"evt-{uuid.UUID(str(event_id))}"
    except ValueError:
        raise PoisonMessageError("event_id must be a UUID") from None
    if not isinstance(record, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in record.items()
    ):
        raise PoisonMessageError("record must be an object of strings")
    try:
        content = rows_to_csv([record])
        receipt = ArtifactService(engine).ingest(
            tenant_id=tenant_id,
            source=source,
            provider_id=provider_id,
            idempotency_key=key,
            content=content,
            actor=f"svc-ingest-{source.value}",
            correlation_id=key[:64],
            now=datetime.now(UTC),
        )
    except ArtifactError as exc:
        raise PoisonMessageError(str(exc)) from None
    except IdempotencyConflictError:
        return "conflict"
    if receipt.replayed:
        return "replayed"
    return "accepted" if receipt.accepted else "rejected"


@dataclass
class Worker:
    engine: Engine
    nc: NatsClient
    poll_interval: float = 0.5
    stop: asyncio.Event = field(default_factory=asyncio.Event)

    async def _relay_loop(self, js: JetStreamContext) -> None:
        while not self.stop.is_set():
            try:
                await relay_once(self.engine, js)
            except Exception:
                log.exception("outbox relay pass failed")
            await asyncio.sleep(self.poll_interval)

    async def _dead_letter(
        self, js: JetStreamContext, consumer: str, msg: Msg, reason: str
    ) -> None:
        await js.publish(
            f"{DLQ_PREFIX}.{consumer}",
            json.dumps(
                {"subject": msg.subject, "reason": reason[:300], "data": msg.data.decode()[:4096]},
                separators=(",", ":"),
            ).encode(),
            timeout=5,
        )

    async def _consume(
        self,
        js: JetStreamContext,
        durable: str,
        filter_subject: str,
        stream: str,
        handler: Handler,
        on_exhausted: Callable[[dict[str, object], str], Awaitable[None]] | None = None,
    ) -> None:
        sub = await js.pull_subscribe(
            filter_subject,
            durable=durable,
            stream=stream,
            config=ConsumerConfig(ack_wait=60, max_deliver=MAX_DELIVER),
        )
        while not self.stop.is_set():
            try:
                msgs: list[Msg] = await sub.fetch(batch=10, timeout=1)
            except TimeoutError:
                continue
            for msg in msgs:
                parent = telemetry.context_from((msg.headers or {}).get(telemetry.TRACEPARENT))
                with telemetry.tracer().start_as_current_span(
                    f"process {durable}",
                    kind=SpanKind.CONSUMER,
                    context=parent,
                    attributes={
                        "messaging.system": "nats",
                        "messaging.consumer.group.name": durable,
                    },
                ) as span:
                    await self._handle(js, durable, msg, handler, on_exhausted, span)

    async def _handle(
        self,
        js: JetStreamContext,
        durable: str,
        msg: Msg,
        handler: Handler,
        on_exhausted: Callable[[dict[str, object], str], Awaitable[None]] | None,
        span: Span,
    ) -> None:
        try:
            if len(msg.data) > MAX_EVENT_BYTES:
                raise PoisonMessageError("event exceeds size limit")
            envelope = json.loads(msg.data)
            if not isinstance(envelope, dict):
                raise PoisonMessageError("envelope must be a JSON object")
            result = await asyncio.to_thread(handler, self.engine, envelope, msg.subject)
            await msg.ack()
            span.set_attribute("recon.result", result)
            log.info("event handled", extra={"consumer": durable, "result": result})
        except (PoisonMessageError, json.JSONDecodeError) as exc:
            span.set_attribute("recon.result", "dead_lettered")
            await self._dead_letter(js, durable, msg, f"poison: {exc}")
            await msg.term()
            log.warning("poison message dead-lettered", extra={"consumer": durable})
        except Exception as exc:
            span.set_status(StatusCode.ERROR, type(exc).__name__)
            deliveries = msg.metadata.num_delivered
            if deliveries >= MAX_DELIVER:
                await self._dead_letter(js, durable, msg, f"exhausted: {type(exc).__name__}")
                if on_exhausted is not None:
                    await on_exhausted(json.loads(msg.data), type(exc).__name__)
                await msg.term()
            else:
                await msg.nak(delay=min(30, 2**deliveries))
            log.warning("event handling failed", extra={"consumer": durable})

    async def _heartbeat_loop(self) -> None:
        instance = f"{socket.gethostname()}-{os.getpid()}"
        while not self.stop.is_set():
            try:
                await asyncio.to_thread(beat, self.engine, "worker", instance, datetime.now(UTC))
            except Exception:
                log.exception("heartbeat failed")
            await asyncio.sleep(HEARTBEAT_SECONDS)

    async def _run_exhausted(self, envelope: dict[str, object], error: str) -> None:
        payload = envelope.get("payload")
        if isinstance(payload, dict) and "run_id" in payload:
            service = ReconciliationService(self.engine)
            await asyncio.to_thread(service.fail_run, uuid.UUID(str(payload["run_id"])), error)

    async def run(self) -> None:
        js = self.nc.jetstream()
        await ensure_stream(js)
        await asyncio.gather(
            self._heartbeat_loop(),
            self._relay_loop(js),
            self._consume(
                js,
                RUN_CONSUMER,
                subject(RECONCILIATION_REQUESTED),
                STREAM,
                handle_run_requested,
                self._run_exhausted,
            ),
            self._consume(
                js, INGEST_CONSUMER, f"{INGEST_PREFIX}.>", INGEST_STREAM, handle_observation_event
            ),
        )
