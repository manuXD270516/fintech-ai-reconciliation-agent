"""Suite results, manifest-driven gates, reports and regression comparison."""

from __future__ import annotations

import json
import operator
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

MANIFESTS = Path(__file__).resolve().parent / "manifests"
OPS: dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
}
REGRESSION_TOLERANCE = 0.02


@dataclass
class GateResult:
    metric: str
    op: str
    threshold: float
    value: float | None
    critical: bool
    passed: bool


@dataclass
class SuiteResult:
    suite: str
    label: str  # MEASURED | SIMULATED | SKIPPED
    metrics: dict[str, Any]
    manifest: dict[str, Any] = field(default_factory=dict)
    gates: list[GateResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.label == "SKIPPED":
            return "SKIPPED"
        return "FAIL" if any(g.critical and not g.passed for g in self.gates) else "PASS"


def load_manifest(suite: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MANIFESTS / f"{suite}.json").read_text(encoding="utf-8"))
    return data


def lookup(metrics: dict[str, Any], dotted: str) -> float | None:
    value: Any = metrics
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return float(value) if isinstance(value, int | float) else None


def apply_gates(result: SuiteResult) -> SuiteResult:
    for gate in result.manifest.get("gates", []):
        value = lookup(result.metrics, gate["metric"])
        passed = value is not None and OPS[gate["op"]](value, float(gate["threshold"]))
        result.gates.append(
            GateResult(gate["metric"], gate["op"], float(gate["threshold"]), value,
                       bool(gate["critical"]), passed)
        )  # fmt: skip
    return result


def to_json(results: list[SuiteResult], context: dict[str, Any]) -> dict[str, Any]:
    suites = []
    for r in results:
        body = asdict(r) | {"status": r.status}
        suites.append(body)
    blocking = [g for r in results for g in r.gates if g.critical and not g.passed]
    return {
        **context,
        "overall": "FAIL" if blocking else "PASS",
        "blocking_gates": [asdict(g) for g in blocking],
        "suites": suites,
    }


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Reporte de evaluación",
        "",
        f"Commit `{report['commit']}` (dirty: {report['dirty']}), generado "
        f"{report['generated_utc']} en {report['host']}. Resultado global: "
        f"**{report['overall']}**.",
        "",
        "Etiquetas: MEASURED = componente real ejecutado sobre datos sintéticos; SIMULATED = "
        "salida de modelo scripted; SKIPPED = dependencia no disponible. Los umbrales son "
        "EXPECTED (manifests) y no son resultados.",
        "",
        "| Suite | Etiqueta | Estado | Gates críticos |",
        "|---|---|---|---|",
    ]
    for s in report["suites"]:
        crit = [g for g in s["gates"] if g["critical"]]
        ok = sum(g["passed"] for g in crit)
        lines.append(f"| {s['suite']} | {s['label']} | {s['status']} | {ok}/{len(crit)} |")
    for s in report["suites"]:
        lines += ["", f"## {s['suite']} ({s['label']})", ""]
        for note in s["notes"]:
            lines.append(f"- {note}")
        if s["gates"]:
            lines += ["", "| Métrica | Condición | Valor | Crítico | OK |", "|---|---|---|---|---|"]
            for g in s["gates"]:
                lines.append(
                    f"| `{g['metric']}` | {g['op']} {g['threshold']} | {g['value']} | "
                    f"{'sí' if g['critical'] else 'no'} | {'✔' if g['passed'] else '✘'} |"
                )
    return "\n".join(lines) + "\n"


def tracked(report: dict[str, Any]) -> dict[str, float]:
    """Gate metrics of non-skipped suites, keyed `suite:metric`, for regression checks."""
    out: dict[str, float] = {}
    for s in report["suites"]:
        if s["label"] == "SKIPPED":
            continue
        for g in s["gates"]:
            if g["value"] is not None:
                out[f"{s['suite']}:{g['metric']}"] = float(g["value"])
    return out


def regressions(
    baseline: dict[str, Any], current: dict[str, Any], tolerance: float = REGRESSION_TOLERANCE
) -> list[str]:
    """A metric regresses when it moves against its gate direction beyond the tolerance."""
    directions = {
        f"{s['suite']}:{g['metric']}": g["op"] for s in current["suites"] for g in s["gates"]
    }
    base, now = tracked(baseline), tracked(current)
    found = []
    for key, old in sorted(base.items()):
        if key not in now:
            continue
        new, op = now[key], directions.get(key, ">=")
        worse = (new < old - tolerance) if op == ">=" else (new > old + tolerance)
        if op == "==" and new != old:
            worse = True
        if worse:
            found.append(f"{key}: {old} -> {new}")
    return found
