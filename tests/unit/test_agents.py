"""M5 T01-T07: routing, planning policy, bounded execution over a real MCP client, the
deterministic evidence phase and adversarial model behaviours (SIMULATED provider).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp import Client

from recon_agents.context import CONTEXT_TOKENS, build
from recon_agents.evidence import Bundle
from recon_agents.models import READ_TOOLS, Budget, CaseSnapshot
from recon_agents.orchestrator import Investigator, MemoryStore
from recon_agents.providers import (
    Behaviour,
    ModelRequest,
    OllamaProvider,
    Purpose,
    ScriptedProvider,
    estimate_tokens,
    provider_from_env,
)
from recon_agents.routing import route
from recon_agents.tool_client import McpToolClient, server_environment
from recon_mcp.backend import MemoryBackend
from recon_mcp.contracts import CATALOG, Scope
from recon_mcp.identity import ServiceIdentity
from recon_mcp.server import build_server
from recon_mcp.tools import Limits, ToolService

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mcp_fixture.json"
CASE = CaseSnapshot(
    case_ref="55555555-5555-4555-8555-555555555555#2",
    case_version=1,
    tenant_id="tenant-demo",
    batch_id="b-alfa-01-usd",
    run_id="55555555-5555-4555-8555-555555555555",
    ordinal=2,
    payment_ref="pay-0042",
    operation_type="capture",
    match_status="UNMATCHED",
    rule="strong_ref_linked",
    discrepancy_types=("AMOUNT_MISMATCH",),
    amount_difference_minor=-100,
    provider_id="prov-alfa",
    merchant_account="merchant-01",
    currency="USD",
    occurred_at="2026-09-01T12:00:00+00:00",
    left_transaction_ids=("11111111-1111-4111-8111-111111111111",),
    right_transaction_ids=("22222222-2222-4222-8222-222222222222",),
)


@asynccontextmanager
async def agent(
    behaviour: Behaviour = Behaviour.FAITHFUL,
    limits: Limits | None = None,
    budget: Budget | None = None,
    delay: float = 0.0,
) -> AsyncIterator[tuple[Investigator, ScriptedProvider, MemoryStore, ToolService]]:
    backend = MemoryBackend(json.loads(FIXTURE.read_text(encoding="utf-8")))
    backend.delay = delay
    service = ToolService(backend, ServiceIdentity("svc-agent", "tenant-demo", frozenset(Scope)),
                          limits, cursor_key=b"k" * 32)  # fmt: skip
    provider, store = ScriptedProvider(behaviour), MemoryStore()
    async with Client(build_server(service), mode="legacy") as client:
        investigator = Investigator(
            McpToolClient(client), provider, store, (lambda: budget) if budget else Budget
        )
        yield investigator, provider, store, service


@pytest.mark.parametrize(
    ("changes", "investigate", "reason"),
    [
        ({"match_status": "EXACT", "discrepancy_types": ()}, False, "exact_match"),
        ({"discrepancy_types": ("WAITING_SOURCE",)}, False, "waiting_source"),
        ({"discrepancy_types": ("MISSING_EXTERNAL",)}, False, "deterministic_missing"),
        ({"match_status": "PROBABLE", "discrepancy_types": ()}, True, "ambiguous_candidates"),
        ({"discrepancy_types": ("PROCESSING_ERROR",)}, True, "unknown_status"),
        ({"discrepancy_types": ("DUPLICATE_CANDIDATE",)}, True, "duplicate_context"),
        ({}, True, "needs_context"),
    ],
)
def test_routing_requires_an_explicit_reason(
    changes: dict[str, Any], investigate: bool, reason: str
) -> None:
    decision = route(replace(CASE, **changes))
    assert (decision.investigate, decision.reason) == (investigate, reason)


async def test_exact_match_costs_zero_model_and_tool_calls() -> None:
    async with agent() as (investigator, provider, store, service):
        exact = replace(CASE, match_status="EXACT", discrepancy_types=())
        record = await investigator.run(exact, "ana")
    assert record["state"] == "NOT_NEEDED" and record["draft"] is None
    assert provider.calls == [] and record["budget"]["tool_calls"] == 0
    assert store.history[-1][1] == "NOT_NEEDED"


async def test_faithful_investigation_separates_facts_inferences_and_hypotheses() -> None:
    async with agent() as (investigator, provider, store, service):
        record = await investigator.run(CASE, "ana")
    draft = record["draft"]
    assert record["state"] == "DRAFTED", record["issues"]
    assert draft["status"] == "DRAFT" and draft["operational_effect"] == "none"
    assert draft["label"] == "SIMULATED"
    fact_text = " ".join(f["statement"] for f in draft["facts"])
    assert "10000" in fact_text and "9900" in fact_text and "-100" in fact_text
    assert [h["kind"] for h in draft["hypotheses"]] == ["HYPOTHESIS"]  # AG01: never a FACT
    assert "INC-0815" in draft["hypotheses"][0]["statement"]
    refs = {c["ref"] for c in draft["citations"]}
    assert all(r in refs for claim in draft["facts"] for r in claim["evidence_refs"])
    assert draft["confidence_assessment"]["calibration"] == "uncalibrated"
    assert draft["recommended_next_step"] == "REQUEST_PROVIDER_INFO"
    usage = record["budget"]
    assert usage["tool_calls"] <= 6 and usage["generative_calls"] == 2
    assert usage["tokens"] <= usage["max_tokens"] and usage["tokens_estimated"] is True
    assert {s["origin"] for s in record["plan"]} == {"template", "model"}
    assert [s for _, s in store.history] == ["REQUESTED", "PLANNED", "EXECUTED", "DRAFTED"]


async def test_ag02_injected_instructions_never_reach_tools_or_actions() -> None:
    async with agent(Behaviour.INJECTION_FOLLOWER) as (investigator, provider, store, service):
        record = await investigator.run(CASE, "ana")
        tools = (await investigator.tools.client.list_tools()).tools  # type: ignore[attr-defined]
    rejected = {(r["tool"], r["reason"]) for r in record["rejected_steps"]}
    assert ("approve_resolution", "tool_not_in_read_catalog") in rejected
    assert ("fetch_url", "tool_not_in_read_catalog") in rejected
    assert {s["tool"] for s in record["steps"]} <= set(READ_TOOLS)
    assert record["state"] == "ABSTAINED"
    assert record["draft"]["recommended_next_step"] == "HUMAN_REVIEW"
    assert any("not an allowed action" in i for i in record["issues"])
    assert [t.name for t in tools] == list(CATALOG)
    assert record["draft"]["untrusted_content_warnings"]


async def test_hallucinated_facts_are_rejected_and_force_abstention() -> None:
    async with agent(Behaviour.HALLUCINATOR) as (investigator, provider, store, service):
        record = await investigator.run(CASE, "ana")
    assert record["state"] == "ABSTAINED"
    issues = " ".join(record["issues"])
    assert "FACT backed only by documents" in issues and "unresolvable citation" in issues
    statements = " ".join(f["statement"] for f in record["draft"]["facts"])
    assert "reembolsó" not in statements and "INC-0815" not in statements


async def test_ag03_tool_timeouts_become_gaps_and_escalation() -> None:
    limits = Limits()
    limits.timeouts = dict.fromkeys(limits.timeouts, 0.05)
    async with agent(limits=limits, delay=0.2) as (investigator, provider, store, service):
        record = await investigator.run(CASE, "ana")
    assert record["state"] in {"ESCALATED", "ABSTAINED"}
    assert all(not s["ok"] and s["error_code"] == "TIMEOUT" for s in record["steps"])
    assert any("TIMEOUT" in m for m in record["draft"]["missing_evidence"])


async def test_endless_planning_is_capped_by_the_tool_budget() -> None:
    async with agent(Behaviour.ENDLESS_PLANNER) as (investigator, provider, store, service):
        record = await investigator.run(CASE, "ana")
    assert record["budget"]["tool_calls"] == 6 and len(record["steps"]) == 6
    reasons = [r["reason"] for r in record["rejected_steps"]]
    assert reasons.count("tool_budget_exhausted") == 9


async def test_malformed_model_output_never_becomes_a_draft_claim() -> None:
    async with agent(Behaviour.MALFORMED) as (investigator, provider, store, service):
        record = await investigator.run(CASE, "ana")
    assert record["state"] == "ABSTAINED"
    assert any(i.startswith("malformed_output") for i in record["issues"])
    assert any("planner output malformed" in i for i in record["issues"])
    assert record["draft"]["facts"] == []


async def test_generative_budget_exhaustion_escalates() -> None:
    async with agent(budget=Budget(max_generative_calls=1)) as (investigator, *_):
        record = await investigator.run(CASE, "ana")
    assert record["state"] == "ESCALATED"
    assert "generative_calls" in record["budget"]["exhausted"]


def test_agent_catalog_mirrors_the_server_catalog() -> None:
    assert READ_TOOLS == CATALOG


def test_context_marks_documents_untrusted_and_respects_budget() -> None:
    bundle = Bundle(documents=[{"evidence_ref": f"doc:d@1#{i}", "document_type": "runbook",
                                "title": "t", "section_path": "p", "untrusted_instructions": False,
                                "content": "x " * 900} for i in range(40)])  # fmt: skip
    context = build(CASE, bundle, "q")
    docs = context["evidence"]["documents"]
    assert docs and docs[0]["content"].startswith("<untrusted_document>")
    assert context["truncated"] and estimate_tokens(str(context)) <= CONTEXT_TOKENS


def test_mcp_server_environment_drops_other_credentials() -> None:
    base = {"APP_DB_PASSWORD": "x", "POSTGRES_PASSWORD": "y", "PATH": "p"}
    env = server_environment("svc-a", "tenant-demo", "knowledge:read", base)
    assert "APP_DB_PASSWORD" not in env and "POSTGRES_PASSWORD" not in env
    assert env["MCP_TENANT_ID"] == "tenant-demo"


async def test_ollama_provider_speaks_http_and_reports_usage() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        body = {"message": {"content": '{"extra_steps": []}'}, "prompt_eval_count": 321,
                "eval_count": 12}  # fmt: skip
        return httpx.Response(200, json=body)

    provider = OllamaProvider("http://127.0.0.1:11434", "qwen2.5:0.5b",
                              transport=httpx.MockTransport(handler))  # fmt: skip
    response = await provider.generate(
        ModelRequest(Purpose.PLAN, "sys", {"case": {}}, {"type": "object"})
    )
    assert response.input_tokens == 321 and response.output_tokens == 12
    assert response.usage_estimated is False and seen["options"]["temperature"] == 0
    with pytest.raises(ValueError, match="loopback"):
        OllamaProvider("https://api.example.com", "m")


def test_provider_selection_defaults_to_scripted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RECON_MODEL_PROVIDER", raising=False)
    assert isinstance(provider_from_env(), ScriptedProvider)
    monkeypatch.setenv("RECON_MODEL_PROVIDER", "openai")
    with pytest.raises(ValueError):
        provider_from_env()
