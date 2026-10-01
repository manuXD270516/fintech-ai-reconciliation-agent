"""Alert rule evaluation over a `/metrics` scrape (rules in infra/observability/alerts.toml).

Deliberately small: instant comparisons against thresholds, exact label matching and an
explicit policy for absent series. No `for:` durations or routing; thresholds are EXPECTED.
"""

from __future__ import annotations

import operator
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from recon_api.metrics import parse

OPS: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}
Severity = Literal["critical", "warning"]


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    metric: str
    op: str
    threshold: float
    severity: Severity
    runbook: str
    summary: str
    absent: Literal["fire", "ok"] = "ok"
    labels: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Rule:
        if raw["op"] not in OPS:
            raise ValueError(f"{raw['name']}: unsupported op {raw['op']!r}")
        if raw.get("absent", "ok") not in ("fire", "ok"):
            raise ValueError(f"{raw['name']}: absent must be 'fire' or 'ok'")
        if raw["severity"] not in ("critical", "warning"):
            raise ValueError(f"{raw['name']}: unknown severity")
        return cls(
            name=str(raw["name"]),
            metric=str(raw["metric"]),
            op=str(raw["op"]),
            threshold=float(raw["threshold"]),
            severity=raw["severity"],
            runbook=str(raw["runbook"]),
            summary=str(raw["summary"]),
            absent=raw.get("absent", "ok"),
            labels={str(k): str(v) for k, v in dict(raw.get("labels", {})).items()},
        )


@dataclass(frozen=True, slots=True)
class Alert:
    rule: str
    severity: Severity
    firing: bool
    value: float | None
    labels: Mapping[str, str]
    summary: str
    runbook: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "firing": self.firing,
            "value": self.value,
            "labels": dict(self.labels),
            "summary": self.summary,
            "runbook": self.runbook,
        }


def load_rules(path: Path) -> list[Rule]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    rules = [Rule.from_dict(raw) for raw in data.get("alert", [])]
    names = [r.name for r in rules]
    if len(names) != len(set(names)):
        raise ValueError("duplicate alert names")
    return rules


def evaluate(exposition: str, rules: Sequence[Rule]) -> list[Alert]:
    samples = parse(exposition)
    alerts: list[Alert] = []
    for rule in rules:
        matching = [
            (labels, value)
            for labels, value in samples.get(rule.metric, [])
            if all(labels.get(k) == v for k, v in rule.labels.items())
        ]
        if not matching:
            absent = Alert(
                rule=rule.name,
                severity=rule.severity,
                firing=rule.absent == "fire",
                value=None,
                labels=rule.labels,
                summary=f"{rule.summary} (series absent)",
                runbook=rule.runbook,
            )
            alerts.append(absent)
            continue
        compare = OPS[rule.op]
        alerts += [
            Alert(
                rule=rule.name,
                severity=rule.severity,
                firing=compare(value, rule.threshold),
                value=value,
                labels=labels,
                summary=rule.summary,
                runbook=rule.runbook,
            )
            for labels, value in matching
        ]
    return alerts


def firing(alerts: Sequence[Alert]) -> list[Alert]:
    return [a for a in alerts if a.firing]
