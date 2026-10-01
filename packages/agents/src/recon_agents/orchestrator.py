"""Persisted, bounded state machine for one investigation (D05: no agent framework).

REQUESTED -> NOT_NEEDED                                   (routing; zero model calls)
REQUESTED -> PLANNED -> EXECUTED -> DRAFTED | ABSTAINED | ESCALATED | FAILED

Every transition is checkpointed through the store. Budgets (tool calls, generative calls,
tokens, wall time) are enforced before each call; exhausting one ends the run explicitly.
The output is a draft with no operational effect.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Protocol

import anyio
from jsonschema import Draft202012Validator
from opentelemetry import trace

from recon_agents.context import SYSTEM, build
from recon_agents.evidence import Bundle, Verified, collect, verify
from recon_agents.models import (
    PLAN_SCHEMA,
    Budget,
    CaseSnapshot,
    State,
    Step,
    StepRecord,
)
from recon_agents.planner import admit, template
from recon_agents.providers import (
    ModelError,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    Purpose,
)
from recon_agents.reviewer import (
    REVIEW_SCHEMA,
    Review,
    combine,
    deterministic_review,
    review_context,
)
from recon_agents.routing import route
from recon_agents.tool_client import ToolClient, ToolOutcome

_tracer = trace.get_tracer("recon")  # no-op unless the process configured the SDK (M9)

QUESTION = (
    "¿Qué evidencia explica el resultado de conciliación y qué falta para que una persona "
    "decida? No recomiendes acciones operativas."
)


class InvestigationStore(Protocol):
    def save(self, record: dict[str, Any]) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.history: list[tuple[str, str]] = []

    def save(self, record: dict[str, Any]) -> None:
        self.records[record["investigation_id"]] = json.loads(json.dumps(record, default=str))
        self.history.append((record["investigation_id"], record["state"]))


class BudgetExhaustedError(Exception):
    pass


class Investigator:
    def __init__(
        self,
        tools: ToolClient,
        provider: ModelProvider,
        store: InvestigationStore,
        budget_factory: Callable[[], Budget] = Budget,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.tools = tools
        self.provider = provider
        self.store = store
        self.budget_factory = budget_factory
        self.clock = clock

    async def run(
        self, case: CaseSnapshot, requested_by: str, investigation_id: str | None = None
    ) -> dict[str, Any]:
        budget = self.budget_factory()
        started = time.perf_counter()
        now = self.clock().isoformat()
        record: dict[str, Any] = {
            "investigation_id": investigation_id or str(uuid.uuid4()),
            "tenant_id": case.tenant_id,
            "case_ref": case.case_ref,
            "case_version": case.case_version,
            "input_snapshot_hash": case.snapshot_hash,
            "requested_by": requested_by,
            "model": self.provider.name,
            "model_kind": self.provider.kind,
            "state": State.REQUESTED.value,
            "reason": None,
            "plan": [],
            "rejected_steps": [],
            "steps": [],
            "issues": [],
            "draft": None,
            "budget": budget.as_dict(),
            "created_at": now,
            "updated_at": now,
        }
        self._checkpoint(record, State.REQUESTED, budget, started)

        decision = route(case)
        record["reason"] = decision.reason
        if not decision.investigate:
            record["issues"].append(decision.explanation)
            return self._checkpoint(record, State.NOT_NEEDED, budget, started)

        try:
            with anyio.fail_after(budget.max_seconds):
                return await self._investigate(case, record, budget, started)
        except TimeoutError:
            budget.exhausted.append("wall_time")
            record["issues"].append("wall-time budget exhausted; escalated to a person")
            return self._checkpoint(record, State.ESCALATED, budget, started)

    async def _investigate(
        self, case: CaseSnapshot, record: dict[str, Any], budget: Budget, started: float
    ) -> dict[str, Any]:
        steps = template(case, str(record["reason"]))
        try:
            proposal = await self._generate(
                Purpose.PLAN,
                {"case": case.as_dict(), "planned": [s.tool for s in steps],
                 "allowed_tools": "read catalog only", "reason": record["reason"]},
                PLAN_SCHEMA,
                budget,
            )  # fmt: skip
            proposals = self._parse(proposal, PLAN_SCHEMA)
            extra, rejected = admit(
                proposals.get("extra_steps", []) if proposals else [],
                case,
                steps,
                budget.max_tool_calls,
            )
            if proposals is None:
                record["issues"].append("planner output malformed; template plan only")
        except (ModelError, BudgetExhaustedError) as exc:
            extra, rejected = [], []
            record["issues"].append(f"planner unavailable ({type(exc).__name__}); template only")
        steps += extra
        record["plan"] = [asdict(s) for s in steps]
        record["rejected_steps"] = [asdict(r) for r in rejected]
        self._checkpoint(record, State.PLANNED, budget, started)

        outcomes: list[tuple[str, dict[str, Any], ToolOutcome]] = []
        for step in steps:
            outcome = await self._call_tool(step, budget, record)
            outcomes.append((step.tool, step.arguments, outcome))
        self._checkpoint(record, State.EXECUTED, budget, started)

        bundle = collect(case, outcomes)
        try:
            raw = await self._generate(
                Purpose.DRAFT, build(case, bundle, QUESTION), {"type": "object"}, budget
            )
        except (ModelError, BudgetExhaustedError) as exc:
            record["issues"].append(f"drafting unavailable ({type(exc).__name__}); escalated")
            return self._checkpoint(record, State.ESCALATED, budget, started)
        checked = verify(self._parse(raw, None), bundle)
        record["issues"] += checked.issues
        record["draft"] = self._draft(case, record, bundle, checked, budget)
        if checked.critical:
            return self._checkpoint(record, State.ABSTAINED, budget, started)
        if bundle.gaps and any("TIMEOUT" in g or "DEPENDENCY" in g for g in bundle.gaps):
            record["issues"].append("evidence gaps from unavailable tools; escalated")
            return self._checkpoint(record, State.ESCALATED, budget, started)
        return await self._review_and_finish(case, record, bundle, checked, budget, started)

    async def _review_and_finish(
        self,
        case: CaseSnapshot,
        record: dict[str, Any],
        bundle: Bundle,
        checked: Verified,
        budget: Budget,
        started: float,
    ) -> dict[str, Any]:
        review = await self._review(case, record["draft"], checked.issues, budget)
        reflectable = review.result == "NEEDS_MORE_EVIDENCE" and (
            review.objections or review.deterministic
        )
        if reflectable and budget.max_generative_calls - budget.generative_calls >= 2:
            record["reflections"] = 1  # one revision at most, only after actionable objections
            context = build(case, bundle, QUESTION) | {
                "reviewer_objections": review.objections,
                "reviewer_findings": review.deterministic,
            }
            raw = await self._generate(Purpose.DRAFT, context, {"type": "object"}, budget)
            checked = verify(self._parse(raw, None), bundle)
            record["issues"] += checked.issues
            record["draft"] = self._draft(case, record, bundle, checked, budget)
            if checked.critical:
                return self._checkpoint(record, State.ABSTAINED, budget, started)
            review = await self._review(case, record["draft"], checked.issues, budget)
        elif reflectable:
            record["issues"].append("reflection does not fit the generative budget")
        record["draft"]["review_result"] = review.as_dict()
        record["draft"]["budget_usage"] = budget.as_dict()
        if review.result == "SUPPORTED":
            state = State.DRAFTED
        elif review.result == "REJECTED":
            state = State.ABSTAINED
            record["issues"].append("reviewer rejected the draft")
        else:
            state = State.ESCALATED
            record["issues"].append("reviewer needs more evidence; escalated to a person")
        return self._checkpoint(record, state, budget, started)

    async def _review(
        self, case: CaseSnapshot, draft: dict[str, Any], issues: list[str], budget: Budget
    ) -> Review:
        base = deterministic_review(case, draft, issues)
        if base.result == "REJECTED":
            return base
        try:
            response = await self._generate(
                Purpose.REVIEW, review_context(case, draft), REVIEW_SCHEMA, budget
            )
        except (ModelError, BudgetExhaustedError):
            return combine(base, None, self.provider.name)
        return combine(base, self._parse(response, REVIEW_SCHEMA), self.provider.name)

    async def _call_tool(self, step: Step, budget: Budget, record: dict[str, Any]) -> ToolOutcome:
        if budget.tool_calls >= budget.max_tool_calls:
            budget.exhausted.append("tool_calls")
            outcome = ToolOutcome(False, {}, "BUDGET_EXHAUSTED")
            record["steps"].append(asdict(StepRecord(step.tool, step.arguments, step.origin,
                                                     False, "BUDGET_EXHAUSTED")))  # fmt: skip
            return outcome
        budget.tool_calls += 1
        t0 = time.perf_counter()
        outcome = await self.tools.call(step.tool, step.arguments)
        refs = [p.get("record_or_chunk_id", "") for p in outcome.payload.get("provenance", [])]
        record["steps"].append(
            asdict(
                StepRecord(
                    step.tool,
                    step.arguments,
                    step.origin,
                    outcome.ok,
                    outcome.error_code,
                    outcome.retryable,
                    round(time.perf_counter() - t0, 4),
                    refs[:20],
                )
            )
        )
        return outcome

    async def _generate(
        self, purpose: Purpose, context: dict[str, Any], schema: dict[str, Any], budget: Budget
    ) -> ModelResponse:
        if budget.generative_calls >= budget.max_generative_calls:
            budget.exhausted.append("generative_calls")
            raise BudgetExhaustedError("generative_calls")
        if budget.tokens >= budget.max_tokens:
            budget.exhausted.append("tokens")
            raise BudgetExhaustedError("tokens")
        budget.generative_calls += 1
        with _tracer.start_as_current_span(
            f"model.generate {purpose.value}",
            attributes={"gen_ai.operation.name": "generate", "recon.purpose": purpose.value},
        ) as span:
            response = await self.provider.generate(ModelRequest(purpose, SYSTEM, context, schema))
            span.set_attributes(
                {
                    "gen_ai.usage.input_tokens": response.input_tokens,
                    "gen_ai.usage.output_tokens": response.output_tokens,
                    "recon.usage_estimated": response.usage_estimated,
                }
            )
        budget.input_tokens += response.input_tokens
        budget.output_tokens += response.output_tokens
        budget.tokens_estimated = budget.tokens_estimated or response.usage_estimated
        return response

    @staticmethod
    def _parse(response: ModelResponse, schema: dict[str, Any] | None) -> Any:
        try:
            value = json.loads(response.text)
        except ValueError:
            return None
        if schema is not None and list(Draft202012Validator(schema).iter_errors(value)):
            return None
        return value

    def _draft(
        self,
        case: CaseSnapshot,
        record: dict[str, Any],
        bundle: Bundle,
        checked: Verified,
        budget: Budget,
    ) -> dict[str, Any]:
        def group(kind: str) -> list[dict[str, Any]]:
            return [asdict(c) for c in checked.claims if c.kind == kind]

        cited = sorted({r for c in checked.claims for r in c.evidence_refs})
        coverage = len(cited) / len(bundle.refs) if bundle.refs else 0.0
        return {
            "status": "DRAFT",
            "operational_effect": "none",
            "label": self.provider.kind,
            "case_id": case.case_ref,
            "case_version": case.case_version,
            "run_id": record["investigation_id"],
            "input_snapshot_hash": case.snapshot_hash,
            "facts": group("FACT"),
            "inferences": group("INFERENCE"),
            "hypotheses": group("HYPOTHESIS"),
            "contradictions": checked.contradictions,
            "missing_evidence": checked.missing_evidence + bundle.gaps,
            "recommended_next_step": checked.next_step,
            "confidence_assessment": {
                "calibration": "uncalibrated",
                "evidence_coverage": round(coverage, 3),
                "contradiction": bool(checked.contradictions),
                "verification_issues": len(checked.issues),
            },
            "citations": [{"ref": r, "provenance": bundle.provenance[r]} for r in cited],
            "untrusted_content_warnings": [w for w in bundle.warnings if "untrusted" in w],
            "review_result": None,
            "budget_usage": budget.as_dict(),
            "summary": checked.summary,
        }

    def _checkpoint(
        self, record: dict[str, Any], state: State, budget: Budget, started: float
    ) -> dict[str, Any]:
        budget.seconds = round(time.perf_counter() - started, 4)
        record["state"] = state.value
        record["budget"] = budget.as_dict()
        record["updated_at"] = self.clock().isoformat()
        self.store.save(record)
        return record
