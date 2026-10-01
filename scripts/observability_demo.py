"""Distributed tracing demo (M9, D09): optional `observability` profile with Jaeger.

    uv run python scripts/observability_demo.py [--out report.json] [--keep]

Starts the OpenTelemetry Collector and Jaeger (this project only), recreates api, worker
and investigator with OTEL_EXPORTER_OTLP_ENDPOINT set, drives one reconciliation run and
one investigation over HTTP, then asks Jaeger's query API for the trace and checks that
a single trace spans recon-api -> recon-worker -> recon-investigator -> fintech-mcp-server
and that no span carries tenant or subject attributes. Unless --keep, the services are
recreated without tracing and the profile is stopped afterwards (default stays off).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import dev_auth  # noqa: E402
from scripts.smoke import Api, SmokeFailure, expect, load_env  # noqa: E402
from scripts.web_e2e import new_batch  # noqa: E402

ENDPOINT = "http://otel-collector:4318"
SERVICES = ("recon-api", "recon-worker", "recon-investigator", "fintech-mcp-server")
FORBIDDEN_TAGS = ("tenant", "subject", "enduser", "authorization", "amount")
TERMINAL = ("NOT_NEEDED", "DRAFTED", "ABSTAINED", "ESCALATED", "FAILED")


def compose(*args: str, tracing: bool) -> None:
    import subprocess  # noqa: PLC0415 - only this helper shells out

    env = dict(os.environ)
    env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    if tracing:
        env["OTEL_EXPORTER_OTLP_ENDPOINT"] = ENDPOINT
    proc = subprocess.run(["docker", "compose", *args], cwd=ROOT, env=env, capture_output=True,
                          text=True, check=False, timeout=900)  # fmt: skip
    expect(proc.returncode == 0, proc.stderr[-1500:])


def jaeger(path: str, port: int) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}{path}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        body: dict[str, Any] = json.loads(resp.read())
    return body


def drive(api: Api) -> dict[str, str]:
    analyst = dev_auth.token("ana-trace", ["analyst"])
    integration = dev_auth.token("svc-trace-ingest", ["integration"])
    batch_id = new_batch(api, analyst, integration, "trace")
    run = api.get(f"/v1/batches/{batch_id}/runs", method="POST", token=analyst)
    expect(run.status == 202, run.text)
    run_id = run.body["run_id"]
    deadline = time.monotonic() + 90
    while api.get(f"/v1/runs/{run_id}", token=analyst).body.get("status") != "completed":
        expect(time.monotonic() < deadline, "run did not complete")
        time.sleep(0.5)
    items = api.get(f"/v1/runs/{run_id}/results?limit=500", token=analyst).body["items"]
    mismatch = next(i for i in items if "AMOUNT_MISMATCH" in i["discrepancy_types"])
    path = f"/v1/runs/{run_id}/results/{mismatch['ordinal']}/investigations"
    requested = api.get(path, method="POST", token=analyst)
    expect(requested.status in (200, 202), requested.text)
    inv = requested.body["investigation_id"]
    while True:
        state = api.get(f"/v1/investigations/{inv}", token=analyst).body["state"]
        if state in TERMINAL:
            break
        expect(time.monotonic() < deadline + 120, "investigation did not finish")
        time.sleep(0.5)
    return {"run_id": run_id, "investigation_id": inv, "state": state}


Span = tuple[str, str, str, list[str]]  # trace id, service, span name, attribute keys


def spans_for(service: str, port: int, since: datetime) -> list[Span]:
    """Jaeger v2 query API (/api/v3, OTLP JSON): every span of the matching traces."""
    query = urllib.parse.urlencode(
        {
            "query.service_name": service,
            "query.start_time_min": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query.start_time_max": (datetime.now(UTC) + timedelta(minutes=5)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "query.num_traces": "100",
        }
    )
    try:
        body = jaeger(f"/api/v3/traces?{query}", port)
    except urllib.error.HTTPError as err:
        if err.code == 404:  # no traces yet for this service
            return []
        raise
    spans: list[Span] = []
    for resource in body.get("result", {}).get("resourceSpans", []):
        attrs = {a["key"]: a["value"] for a in resource["resource"]["attributes"]}
        name = attrs.get("service.name", {}).get("stringValue", "?")
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                keys = [a["key"] for a in span.get("attributes", [])]
                spans.append((span["traceId"], name, span["name"], keys))
    return spans


def inspect_traces(port: int, since: datetime) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while True:
        spans = spans_for("fintech-mcp-server", port, since)
        by_trace: dict[str, set[str]] = {}
        for trace_id, service, _, _ in spans:
            by_trace.setdefault(trace_id, set()).add(service)
        full = [t for t, services in by_trace.items() if services >= set(SERVICES)]
        if full or time.monotonic() > deadline:
            break
        time.sleep(3)
    expect(bool(full), f"no trace spans all services: {by_trace}")
    trace_id = max(full, key=lambda t: sum(1 for s in spans if s[0] == t))
    names: dict[str, set[str]] = {}
    for tid, service, name, _ in spans:
        if tid == trace_id:
            names.setdefault(service, set()).add(name)
    every = spans + spans_for("recon-api", port, since) + spans_for("recon-worker", port, since)
    leaked = sorted(
        {key for *_, keys in every for key in keys if key.lower().startswith(FORBIDDEN_TAGS)}
    )
    expect(not leaked, f"forbidden span attributes: {leaked}")
    return {
        "trace_id": trace_id,
        "span_count": sum(1 for s in spans if s[0] == trace_id),
        "services": sorted(names),
        "operations": {k: sorted(v) for k, v in sorted(names.items())},
        "spans_checked_for_forbidden_attributes": len(every),
        "forbidden_attribute_keys": leaked,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--keep", action="store_true", help="leave tracing on afterwards")
    args = parser.parse_args(argv)
    env = load_env()
    api = Api(int(env.get("API_HOST_PORT", "18180")))
    port = int(env.get("JAEGER_HOST_PORT", "18186"))
    report: dict[str, Any] = {"kind": "MEASURED", "scope": "local Compose, synthetic data"}
    try:
        compose("--profile", "observability", "up", "-d", "otel-collector", "jaeger",
                tracing=True)  # fmt: skip
        compose("up", "-d", "api", "worker", "investigator", tracing=True)
        api.wait_status("/health/ready", 200, timeout=120)
        since = datetime.now(UTC) - timedelta(seconds=5)
        report["driven"] = drive(api)
        report["trace"] = inspect_traces(port, since)
    except SmokeFailure as exc:
        report["error"] = str(exc)
    finally:
        if not args.keep:
            compose("up", "-d", "api", "worker", "investigator", tracing=False)
            compose("--profile", "observability", "stop", "otel-collector", "jaeger",
                    tracing=False)  # fmt: skip
            api.wait_status("/health/ready", 200, timeout=120)
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 1 if "error" in report else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
