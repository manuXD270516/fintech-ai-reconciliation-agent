"""Prometheus text exposition for `/metrics` (M9, D09).

Two sources: in-process HTTP counters/histograms recorded by the request middleware, and
an operational snapshot read at scrape time (PostgreSQL aggregates + JetStream DLQ
depth). Labels are low-cardinality by construction: route templates (never raw paths),
status classes, enum values and tool names. No tenant, subject or resource IDs.
"""

from __future__ import annotations

import asyncio
import math
import threading
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field

from recon_store.ops import OpsSnapshot

BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
UNMATCHED_ROUTE = "unmatched"
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@dataclass
class _Histogram:
    buckets: list[int] = field(default_factory=lambda: [0] * len(BUCKETS))
    total: float = 0.0
    count: int = 0


class HttpMetrics:
    """Thread-safe request counters; one instance per app."""

    def __init__(self) -> None:
        self.ai_enabled = True  # M10 kill switch state, exported as recon_ai_enabled
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._latency: dict[str, _Histogram] = defaultdict(_Histogram)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        status_class = f"{status // 100}xx"
        with self._lock:
            self._requests[(method, route, status_class)] += 1
            hist = self._latency[route]
            for i, bound in enumerate(BUCKETS):
                if seconds <= bound:
                    hist.buckets[i] += 1
            hist.total += seconds
            hist.count += 1

    def lines(self) -> list[str]:
        out = [
            "# HELP recon_ai_enabled 1 while AI investigations are enabled (kill switch).",
            "# TYPE recon_ai_enabled gauge",
            f"recon_ai_enabled {int(self.ai_enabled)}",
            "# HELP recon_http_requests_total HTTP requests by method, route and status class.",
            "# TYPE recon_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status), n in sorted(self._requests.items()):
                labels = _labels(method=method, route=route, status_class=status)
                out.append(f"recon_http_requests_total{labels} {n}")
            out += [
                "# HELP recon_http_request_duration_seconds HTTP request latency by route.",
                "# TYPE recon_http_request_duration_seconds histogram",
            ]
            for route, hist in sorted(self._latency.items()):
                for bound, n in zip(BUCKETS, hist.buckets, strict=True):
                    labels = _labels(route=route, le=_num(bound))
                    out.append(f"recon_http_request_duration_seconds_bucket{labels} {n}")
                labels = _labels(route=route, le="+Inf")
                out.append(f"recon_http_request_duration_seconds_bucket{labels} {hist.count}")
                out.append(
                    f"recon_http_request_duration_seconds_sum{_labels(route=route)} "
                    f"{_num(hist.total)}"
                )
                out.append(
                    f"recon_http_request_duration_seconds_count{_labels(route=route)} {hist.count}"
                )
        return out


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(**labels: str) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{k}="{_escape(v)}"' for k, v in labels.items()) + "}"


def _num(value: float) -> str:
    if math.isinf(value):
        return "+Inf"
    return repr(round(float(value), 6)) if not float(value).is_integer() else str(int(value))


def _metric(
    name: str, kind: str, help_text: str, samples: Iterable[tuple[str, float]]
) -> list[str]:
    return [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}"] + [
        f"{name}{labels} {_num(value)}" for labels, value in samples
    ]


def _by(label: str, values: dict[str, int]) -> list[tuple[str, float]]:
    return [(_labels(**{label: k}), float(v)) for k, v in sorted(values.items())]


def snapshot_lines(snap: OpsSnapshot) -> list[str]:
    lines: list[str] = []
    lines += _metric(
        "recon_outbox_pending", "gauge", "Outbox events not yet published.",
        [("", snap.outbox_pending)],
    )  # fmt: skip
    lines += _metric(
        "recon_outbox_oldest_pending_age_seconds", "gauge",
        "Age of the oldest unpublished outbox event (0 when none).",
        [("", snap.outbox_oldest_pending_seconds)],
    )  # fmt: skip
    lines += _metric(
        "recon_outbox_failed_attempts", "gauge",
        "Failed publish attempts accumulated by unpublished outbox events.",
        [("", snap.outbox_failed_attempts)],
    )  # fmt: skip
    lines += _metric(
        "recon_service_heartbeat_age_seconds", "gauge",
        "Seconds since the last heartbeat of each background service.",
        [(_labels(service=k), v) for k, v in sorted(snap.heartbeat_age_seconds.items())],
    )  # fmt: skip
    lines += _metric(
        "recon_observations", "gauge", "Stored transaction observations.",
        [("", snap.observations)],
    )  # fmt: skip
    lines += _metric(
        "recon_quarantined_rows", "gauge", "Ingestion rows kept in quarantine.",
        [("", snap.quarantined_rows)],
    )  # fmt: skip
    lines += _metric("recon_runs", "gauge", "Reconciliation runs by status.",
                     _by("status", snap.runs))  # fmt: skip
    lines += _metric("recon_match_results", "gauge", "Match results by status.",
                     _by("match_status", snap.results))  # fmt: skip
    lines += _metric("recon_investigations", "gauge", "Investigations by state.",
                     _by("state", snap.investigations))  # fmt: skip
    lines += _metric(
        "recon_investigation_budget_exhausted", "gauge",
        "Investigations that exhausted at least one budget.",
        [("", snap.investigation_budget_exhausted)],
    )  # fmt: skip
    lines += _metric(
        "recon_investigation_tokens", "gauge",
        "Model tokens recorded by investigations (scripted provider: SIMULATED).",
        [("", snap.investigation_tokens)],
    )  # fmt: skip
    lines += _metric("recon_review_results", "gauge", "Independent review results of drafts.",
                     _by("result", snap.review_results))  # fmt: skip
    lines += _metric("recon_cases", "gauge", "Cases by status.", _by("status", snap.cases))
    lines += _metric(
        "recon_human_queue_oldest_age_seconds", "gauge",
        "Age of the oldest pending recommendation awaiting a human decision.",
        [("", snap.human_queue_oldest_seconds)],
    )  # fmt: skip
    lines += _metric(
        "recon_pending_recommendations", "gauge", "Recommendations awaiting a decision.",
        [("", snap.pending_recommendations)],
    )  # fmt: skip
    lines += _metric(
        "recon_decision_denials_last_hour", "gauge",
        "Audited refused decision attempts in the last hour, by reason.",
        _by("reason", snap.decision_denials),
    )  # fmt: skip
    lines += _metric(
        "recon_mcp_tool_calls_last_hour", "gauge",
        "Audited MCP tool calls in the last hour, by tool and outcome.",
        [(_labels(tool=t, outcome=o), n) for (t, o), n in sorted(snap.mcp_tool_calls.items())],
    )  # fmt: skip
    return lines


SnapshotSource = Callable[[], Awaitable[OpsSnapshot]]
DlqSource = Callable[[], Awaitable[int]]


async def render(
    http: HttpMetrics,
    snapshot_source: SnapshotSource | None,
    dlq_source: DlqSource | None,
    deadline: float = 2.0,
) -> str:
    """Collect both sources under a deadline; a failing source reports `up 0`."""
    lines = http.lines()
    up: list[tuple[str, float]] = []
    if snapshot_source is not None:
        try:
            lines += snapshot_lines(await asyncio.wait_for(snapshot_source(), deadline))
            up.append((_labels(source="database"), 1))
        except Exception:
            up.append((_labels(source="database"), 0))
    if dlq_source is not None:
        try:
            depth = await asyncio.wait_for(dlq_source(), deadline)
            lines += _metric(
                "recon_dead_letters_unhandled", "gauge",
                "Dead letters not yet triaged (replayed or discarded) by an operator.",
                [("", depth)],
            )  # fmt: skip
            up.append((_labels(source="messaging"), 1))
        except Exception:
            up.append((_labels(source="messaging"), 0))
    lines += _metric(
        "recon_metrics_source_up", "gauge", "Whether each scrape-time source answered.", up
    )
    return "\n".join(lines) + "\n"


def parse(text: str) -> dict[str, list[tuple[dict[str, str], float]]]:
    """Minimal parser of this module's exposition (used by alert evaluation and tests)."""
    samples: dict[str, list[tuple[dict[str, str], float]]] = defaultdict(list)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, _, value = line.rpartition(" ")
        name, _, rest = head.partition("{")
        labels: dict[str, str] = {}
        if rest:
            for part in rest.rstrip("}").split('",'):
                if "=" in part:
                    key, _, val = part.partition("=")
                    labels[key] = val.strip('"')
        samples[name].append((labels, float(value)))
    return dict(samples)
