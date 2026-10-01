"""M9: metrics exposition, alert rules, trace propagation helpers and DLQ triage parsing."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import get_current_span

from recon_api.alerts import Rule, evaluate, firing, load_rules
from recon_api.metrics import HttpMetrics, parse, render, snapshot_lines
from recon_store import telemetry
from recon_store.ops import OpsSnapshot
from recon_store.tables import outbox
from recon_worker.dlq import REPLAYABLE, DeadLetter
from tests.unit.conftest import Harness

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "infra/observability/alerts.toml"
FORBIDDEN_LABELS = ("tenant", "subject", "transaction", "case_id", "run_id", "user")


def _snapshot(**overrides: object) -> OpsSnapshot:
    base: dict[str, object] = {
        "outbox_pending": 0,
        "heartbeat_age_seconds": {"worker": 3.0, "investigator": 4.0},
        "runs": {"COMPLETED": 2},
        "results": {"EXACT": 10, "UNMATCHED": 2},
        "investigations": {"DRAFTED": 1},
        "review_results": {"SUPPORTED": 1},
        "cases": {"HUMAN_REVIEW": 1},
        "decision_denials": {"SEGREGATION_OF_DUTIES": 1},
        "mcp_tool_calls": {("get_transaction", "ok"): 3},
    }
    return OpsSnapshot(**(base | overrides))  # type: ignore[arg-type]


async def _ok_snapshot() -> OpsSnapshot:
    return _snapshot()


async def _dlq(depth: int = 0) -> int:
    return depth


async def test_metrics_route_uses_templates_never_raw_ids(harness: Harness) -> None:
    run_id = uuid.uuid4()
    async with harness.client() as client:
        await client.get(f"/v1/runs/{run_id}")
        await client.get("/no/such/path/42")
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = response.text
    assert str(run_id) not in body and "/no/such" not in body
    requests = parse(body)["recon_http_requests_total"]
    routes = {labels["route"] for labels, _ in requests}
    assert {"/v1/runs/{run_id}", "unmatched"} <= routes
    assert all(labels["status_class"] in {"2xx", "4xx", "5xx"} for labels, _ in requests)


def test_snapshot_exposition_is_low_cardinality_and_parseable() -> None:
    lines = snapshot_lines(_snapshot())
    text = "\n".join(lines)
    samples = parse(text)
    assert samples["recon_service_heartbeat_age_seconds"] == [
        ({"service": "investigator"}, 4.0),
        ({"service": "worker"}, 3.0),
    ]
    assert ({"tool": "get_transaction", "outcome": "ok"}, 3.0) in samples[
        "recon_mcp_tool_calls_last_hour"
    ]
    label_names = set(re.findall(r'[{,]([a-z_]+)="', text))
    assert not [n for n in label_names if n.startswith(FORBIDDEN_LABELS)]
    assert all(line.startswith(("# HELP", "# TYPE", "recon_")) for line in lines)


async def test_failing_sources_report_down_without_failing_the_scrape() -> None:
    async def broken() -> OpsSnapshot:
        raise ConnectionError("db down")

    async def hanging() -> int:
        await asyncio.sleep(3600)
        return 0

    body = await render(HttpMetrics(), broken, hanging, deadline=0.05)
    up = dict((labels["source"], value) for labels, value in parse(body)["recon_metrics_source_up"])
    assert up == {"database": 0.0, "messaging": 0.0}
    assert "recon_outbox_pending" not in body


async def test_healthy_scrape_marks_sources_up() -> None:
    body = await render(HttpMetrics(), _ok_snapshot, lambda: _dlq(2))
    samples = parse(body)
    assert samples["recon_dead_letters_unhandled"] == [({}, 2.0)]
    assert {v for _, v in samples["recon_metrics_source_up"]} == {1.0}


def test_alert_rules_file_is_valid_and_runbooks_exist() -> None:
    rules = load_rules(RULES)
    assert {r.name for r in rules} >= {
        "OutboxStalled",
        "DeadLetters",
        "WorkerHeartbeatMissing",
        "HumanBacklog",
        "ToolPermissionRefused",
        "MetricsSourceDown",
    }
    for rule in rules:
        assert (ROOT / rule.runbook).is_file(), rule.runbook


async def _exposition(snapshot: OpsSnapshot, dlq: int = 0) -> str:
    async def source() -> OpsSnapshot:
        return snapshot

    return await render(HttpMetrics(), source, lambda: _dlq(dlq))


async def test_alerts_quiet_on_a_healthy_system() -> None:
    alerts = evaluate(await _exposition(_snapshot()), load_rules(RULES))
    assert firing(alerts) == []


@pytest.mark.parametrize(
    ("overrides", "dlq", "expected"),
    [
        ({"outbox_pending": 3, "outbox_oldest_pending_seconds": 61.0}, 0, "OutboxStalled"),
        ({}, 1, "DeadLetters"),
        ({"heartbeat_age_seconds": {"investigator": 1.0}}, 0, "WorkerHeartbeatMissing"),
        ({"heartbeat_age_seconds": {"worker": 90.0, "investigator": 1.0}}, 0,
         "WorkerHeartbeatMissing"),
        ({"human_queue_oldest_seconds": 86_401.0}, 0, "HumanBacklog"),
        ({"mcp_tool_calls": {("get_transaction", "FORBIDDEN"): 1}}, 0, "ToolPermissionRefused"),
    ],
)  # fmt: skip
async def test_each_fault_fires_its_alert(
    overrides: dict[str, object], dlq: int, expected: str
) -> None:
    alerts = evaluate(await _exposition(_snapshot(**overrides), dlq), load_rules(RULES))
    assert [a.rule for a in firing(alerts)] == [expected]


def test_absent_policy_and_rule_validation() -> None:
    rule = Rule.from_dict(
        {"name": "X", "metric": "m", "op": ">", "threshold": 1, "severity": "warning",
         "runbook": "r", "summary": "s", "absent": "fire"}
    )  # fmt: skip
    assert firing(evaluate("", [rule]))[0].value is None
    with pytest.raises(ValueError, match="unsupported op"):
        Rule.from_dict({"name": "Y", "metric": "m", "op": "~", "threshold": 1,
                        "severity": "warning", "runbook": "r", "summary": "s"})  # fmt: skip


def test_traceparent_round_trip_and_off_by_default() -> None:
    assert telemetry.current_traceparent() is None  # no active span: nothing is written
    assert telemetry.enabled({}) is False
    assert telemetry.enabled({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://c:4318",
                              "RECON_TELEMETRY": "off"}) is False  # fmt: skip
    assert telemetry.enabled({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://c:4318"}) is True
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("parent") as span:
        value = telemetry.current_traceparent()
        headers = telemetry.headers_with_trace({"Nats-Msg-Id": "x"})
    assert value is not None and re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", value)
    assert headers == {"Nats-Msg-Id": "x", "traceparent": value}
    ctx = telemetry.context_from(value)
    assert ctx is not None
    assert get_current_span(ctx).get_span_context().trace_id == span.get_span_context().trace_id
    assert telemetry.context_from(None) is None
    assert telemetry.context_from("garbage") is None


def test_outbox_rows_capture_the_active_trace() -> None:
    default = outbox.c.trace_context.default
    assert default is not None and default.is_callable


def test_dead_letter_parsing_and_tenant_attribution() -> None:
    raw_ingest = {
        "subject": "recon.ingest.t-1.provider.prov-a",
        "reason": "poison: x",
        "data": "{}",
    }
    ingest = DeadLetter.parse(7, json.dumps(raw_ingest).encode())
    assert ingest.tenant() == "t-1" and ingest.summary()["replayable"] is True
    raw_event = {
        "subject": "recon.events.ReconciliationRequested",
        "reason": "exhausted",
        "data": json.dumps({"tenant_id": "t-2"}),
    }
    event = DeadLetter.parse(8, json.dumps(raw_event).encode())
    assert event.tenant() == "t-2"
    junk = DeadLetter.parse(9, b"not json")
    assert junk.tenant() == "_system" and junk.summary()["replayable"] is False
    assert all(prefix.startswith("recon.") for prefix in REPLAYABLE)
