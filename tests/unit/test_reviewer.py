"""M6 T01/T02: reviewer (deterministic first, isolated model review) and bounded reflection."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import Client

from recon_agents.models import Budget
from recon_agents.orchestrator import Investigator, MemoryStore
from recon_agents.providers import Behaviour, Purpose, ScriptedProvider
from recon_agents.reviewer import Review, combine, deterministic_review, review_context
from recon_agents.tool_client import McpToolClient
from recon_mcp.backend import MemoryBackend
from recon_mcp.contracts import Scope
from recon_mcp.identity import ServiceIdentity
from recon_mcp.server import build_server
from recon_mcp.tools import ToolService

from .test_agents import CASE

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mcp_fixture.json"


@asynccontextmanager
async def investigator(
    behaviour: Behaviour, budget: Budget | None = None
) -> AsyncIterator[tuple[Investigator, ScriptedProvider]]:
    backend = MemoryBackend(json.loads(FIXTURE.read_text(encoding="utf-8")))
    service = ToolService(backend, ServiceIdentity("svc-agent", "tenant-demo", frozenset(Scope)),
                          cursor_key=b"k" * 32)  # fmt: skip
    provider = ScriptedProvider(behaviour)
    async with Client(build_server(service), mode="legacy") as client:
        factory = (lambda: budget) if budget else Budget
        yield Investigator(McpToolClient(client), provider, MemoryStore(), factory), provider


async def test_one_reflection_after_actionable_objection_when_budget_allows() -> None:
    async with investigator(Behaviour.OBJECTS_ONCE, Budget(max_generative_calls=5)) as (inv, p):
        record = await inv.run(CASE, "ana")
    assert record["reflections"] == 1 and p.reviews == 2
    assert record["state"] == "DRAFTED"
    assert record["draft"]["review_result"]["result"] == "SUPPORTED"
    assert record["budget"]["generative_calls"] == 5


async def test_no_reflection_beyond_the_default_budget_escalates() -> None:
    async with investigator(Behaviour.OBJECTS_ONCE) as (inv, p):
        record = await inv.run(CASE, "ana")
    assert "reflections" not in record and p.reviews == 1
    assert record["state"] == "ESCALATED"
    assert "reflection does not fit the generative budget" in record["issues"]
    assert record["draft"]["review_result"]["result"] == "NEEDS_MORE_EVIDENCE"
    assert record["budget"]["generative_calls"] <= record["budget"]["max_generative_calls"]


async def test_rejecting_reviewer_forces_abstention() -> None:
    async with investigator(Behaviour.REJECTING_REVIEWER) as (inv, _):
        record = await inv.run(CASE, "ana")
    assert record["state"] == "ABSTAINED"
    review = record["draft"]["review_result"]
    assert review["result"] == "REJECTED" and review["objections"]
    assert review["is_human_approval"] is False


async def test_model_reviewer_input_is_isolated() -> None:
    async with investigator(Behaviour.FAITHFUL) as (inv, provider):
        await inv.run(CASE, "ana")
    [request] = [r for r in provider.calls if r.purpose is Purpose.REVIEW]
    assert set(request.context) == {"case", "claims", "citations", "missing_evidence",
                                    "verification_issues", "instructions"}  # fmt: skip
    blob = json.dumps(request.context)
    assert "extra_steps" not in blob and "untrusted_document" not in blob


def test_deterministic_review_requires_elements_and_rejects_contradictions() -> None:
    draft = {"facts": [{"claim_id": "c1", "evidence_refs": ["tx:a@1"]}], "hypotheses": [
        {"claim_id": "h1"}], "contradictions": []}  # fmt: skip
    review = deterministic_review(CASE, draft, [])
    assert review.result == "NEEDS_MORE_EVIDENCE"
    assert any("amount difference" in f for f in review.deterministic)
    assert any("both sides" in f for f in review.deterministic)
    assert any("h1 lacks" in f for f in review.deterministic)
    contradicted = deterministic_review(CASE, draft | {"contradictions": ["x"]}, [])
    assert contradicted.result == "REJECTED"


def test_combination_is_the_most_conservative() -> None:
    ok = Review("SUPPORTED")
    assert combine(ok, {"result": "REJECTED", "objections": []}, "m").result == "REJECTED"
    assert combine(Review("NEEDS_MORE_EVIDENCE"), {"result": "SUPPORTED", "objections": []},
                   "m").result == "NEEDS_MORE_EVIDENCE"  # fmt: skip
    assert combine(ok, None, "m").result == "NEEDS_MORE_EVIDENCE"
    assert set(review_context(CASE, {})["claims"]) == {"facts", "inferences", "hypotheses"}
