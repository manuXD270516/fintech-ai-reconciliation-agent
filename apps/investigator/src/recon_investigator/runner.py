"""JetStream consumer of `InvestigationRequested` (at-least-once, idempotent by state)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from nats.aio.client import Client as NatsClient
from nats.aio.msg import Msg
from nats.js.api import ConsumerConfig
from opentelemetry.trace import Span, SpanKind, StatusCode
from sqlalchemy import Engine

from recon_agents.models import CaseSnapshot
from recon_agents.orchestrator import Investigator
from recon_agents.providers import ModelProvider, provider_from_env
from recon_agents.tool_client import ToolClient, stdio_tool_client
from recon_mcp.contracts import Scope
from recon_store import telemetry
from recon_store.investigations import INVESTIGATION_REQUESTED, TERMINAL, InvestigationRepository
from recon_store.ops import beat

STREAM = "RECON_EVENTS"
CONSUMER = "investigation-runner"
SUBJECT = f"recon.events.{INVESTIGATION_REQUESTED}"
SUBJECT_ID = "svc-investigator"
MAX_DELIVER = 3
HEARTBEAT_SECONDS = 10.0

log = logging.getLogger("recon_investigator")
ToolsFactory = Callable[[str], AbstractAsyncContextManager[ToolClient]]


def default_tools(tenant_id: str) -> AbstractAsyncContextManager[ToolClient]:
    scopes = ",".join(s.value for s in Scope)
    return stdio_tool_client(SUBJECT_ID, tenant_id, scopes)


async def execute(
    engine: Engine,
    investigation_id: uuid.UUID,
    provider_factory: Callable[[], ModelProvider] = provider_from_env,
    tools_factory: ToolsFactory = default_tools,
) -> str:
    repo = InvestigationRepository(engine)
    row = await asyncio.to_thread(repo.load_for_execution, investigation_id)
    if row is None:
        return "unknown"
    if row["state"] in TERMINAL:
        return "duplicate"
    if not await asyncio.to_thread(repo.claim, investigation_id, f"{SUBJECT_ID}-{os.getpid()}"):
        return "duplicate"  # another process holds a live lease
    case = CaseSnapshot.from_dict(row["record"]["snapshot"])
    async with tools_factory(case.tenant_id) as tools:
        investigator = Investigator(tools, provider_factory(), repo)
        record = await investigator.run(case, row["requested_by"], str(investigation_id))
    return str(record["state"])


def mark_failed(engine: Engine, investigation_id: uuid.UUID, reason: str) -> None:
    repo = InvestigationRepository(engine)
    row = repo.load_for_execution(investigation_id)
    if row is None or row["state"] in TERMINAL:
        return
    record: dict[str, Any] = dict(row["record"])
    record |= {
        "investigation_id": str(investigation_id),
        "tenant_id": row["tenant_id"],
        "case_version": row["case_version"],
        "state": "FAILED",
        "model": record.get("model", "n/a"),
        "budget": record.get("budget", {"tool_calls": 0, "generative_calls": 0}),
        "issues": [*record.get("issues", []), f"failed after retries: {reason}"],
    }
    repo.save(record)


@dataclass
class Runner:
    engine: Engine
    nc: NatsClient
    stop: asyncio.Event = field(default_factory=asyncio.Event)

    async def messages(self) -> AsyncIterator[Msg]:
        js = self.nc.jetstream()
        sub = await js.pull_subscribe(
            SUBJECT,
            durable=CONSUMER,
            stream=STREAM,
            config=ConsumerConfig(ack_wait=180, max_deliver=MAX_DELIVER),
        )
        while not self.stop.is_set():
            try:
                for msg in await sub.fetch(batch=1, timeout=1):
                    yield msg
            except TimeoutError:
                continue

    async def heartbeat(self) -> None:
        instance = f"{socket.gethostname()}-{os.getpid()}"
        while not self.stop.is_set():
            try:
                await asyncio.to_thread(
                    beat, self.engine, "investigator", instance, datetime.now(UTC)
                )
            except Exception:
                log.exception("heartbeat failed")
            await asyncio.sleep(HEARTBEAT_SECONDS)

    async def run(self) -> None:
        beating = asyncio.create_task(self.heartbeat())
        try:
            async for msg in self.messages():
                parent = telemetry.context_from((msg.headers or {}).get(telemetry.TRACEPARENT))
                with telemetry.tracer().start_as_current_span(
                    f"process {CONSUMER}",
                    kind=SpanKind.CONSUMER,
                    context=parent,
                    attributes={
                        "messaging.system": "nats",
                        "messaging.consumer.group.name": CONSUMER,
                    },
                ) as span:
                    await self.handle(msg, span)
        finally:
            beating.cancel()

    async def handle(self, msg: Msg, span: Span) -> None:
        try:
            envelope = json.loads(msg.data)
            investigation_id = uuid.UUID(str(envelope["payload"]["investigation_id"]))
        except (ValueError, KeyError, TypeError):
            await msg.term()
            span.set_attribute("recon.result", "malformed")
            log.warning("malformed investigation event terminated")
            return
        span.set_attribute("recon.investigation_id", str(investigation_id))
        try:
            result = await execute(self.engine, investigation_id)
            await msg.ack()
            span.set_attribute("recon.result", result)
            log.info("investigation handled", extra={"result": result})
        except Exception as exc:
            span.set_status(StatusCode.ERROR, type(exc).__name__)
            if msg.metadata.num_delivered >= MAX_DELIVER:
                await asyncio.to_thread(
                    mark_failed, self.engine, investigation_id, type(exc).__name__
                )
                await msg.term()
            else:
                await msg.nak(delay=5)
            log.warning("investigation failed", extra={"error": type(exc).__name__})
