import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ResultRow } from "../api/client";
import { explain } from "../api/client";
import { decode } from "../auth";
import { DECISION_EFFECT, DecisionForm } from "../components";
import { DraftView, ResultsTable } from "../views";

const draft = {
  facts: [
    {
      claim_id: "c1",
      kind: "FACT",
      statement: "internal_ledger registra pay-0042 por 10000 USD.",
      evidence_refs: ["tx:abc@2"],
      limitations: "",
    },
  ],
  inferences: [],
  hypotheses: [
    {
      claim_id: "h1",
      kind: "HYPOTHESIS",
      statement: "Podría relacionarse con INC-0815.",
      evidence_refs: ["doc:incident-inc-0815@1#c"],
      limitations: "Un incidente similar no prueba causalidad.",
      needed_evidence: "Reporte corregido del proveedor",
    },
  ],
  citations: [
    { ref: "tx:abc@2", provenance: { locator: "internal_ledger/led-1@2", effective_at: "2026-09-01" } },
  ],
  missing_evidence: ["Plan de liquidación"],
  recommended_next_step: "REQUEST_PROVIDER_INFO",
  label: "SIMULATED",
  operational_effect: "none",
  confidence_assessment: { calibration: "uncalibrated", evidence_coverage: 0.5 },
  review_result: { result: "SUPPORTED", objections: [] },
  untrusted_content_warnings: ["untrusted_instructions:c-evil"],
};

describe("DraftView", () => {
  it("separates facts, inferences and hypotheses with resolvable citations", () => {
    render(<DraftView draft={draft} />);
    const facts = screen.getByRole("region", { name: "Hechos (FACT)" });
    expect(within(facts).getByText(/10000 USD/)).toBeInTheDocument();
    expect(within(facts).getByText(/internal_ledger\/led-1@2/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Inferencias (INFERENCE)" })).toHaveTextContent(
      "Sin afirmaciones",
    );
    const hypotheses = screen.getByRole("region", { name: "Hipótesis (HYPOTHESIS)" });
    expect(hypotheses).toHaveTextContent("Evidencia necesaria: Reporte corregido");
    expect(within(hypotheses).getByText(/cita no resuelta/)).toBeInTheDocument();
    expect(screen.getByText("uncalibrated")).toBeInTheDocument();
    expect(screen.getByText("SIMULATED")).toBeInTheDocument();
    expect(screen.getByText(/instrucciones no confiables/)).toBeInTheDocument();
    expect(screen.getByText(/no es una aprobación humana/)).toBeInTheDocument();
  });
});

describe("DecisionForm", () => {
  it("states the exact effect, requires a reason and sends version and idempotency key", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<DecisionForm caseVersion={2} runIsLatest onSubmit={onSubmit} />);
    expect(screen.getByText(DECISION_EFFECT)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Registrar decisión" }));
    expect(screen.getByRole("alert")).toHaveTextContent("mínimo 10 caracteres");
    expect(onSubmit).not.toHaveBeenCalled();
    await user.click(screen.getByRole("radio", { name: "Rechazar" }));
    await user.type(screen.getByLabelText("Motivo (obligatorio)"), "evidencia insuficiente");
    await user.click(screen.getByRole("button", { name: "Registrar decisión" }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        decision: "REJECT",
        reason: "evidencia insuficiente",
        expected_version: 2,
        idempotency_key: expect.stringMatching(/^web-/),
      }),
    );
  });

  it("blocks decisions on obsolete cases", () => {
    render(<DecisionForm caseVersion={3} runIsLatest={false} onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Registrar decisión" })).toBeDisabled();
    expect(screen.getByText(/no es aprobable/)).toBeInTheDocument();
  });

  it("is fully operable with the keyboard", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<DecisionForm caseVersion={2} runIsLatest onSubmit={onSubmit} />);
    await user.tab(); // radio group
    await user.keyboard("{ArrowDown}"); // REJECT
    await user.tab(); // reason
    await user.keyboard("motivo escrito por teclado");
    await user.tab(); // submit
    await user.keyboard("{Enter}");
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ decision: "REJECT" }));
  });
});

describe("ResultsTable", () => {
  it("opens a result detail with the keyboard", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    const row: ResultRow = {
      ordinal: 1,
      payment_ref: "pay-0042",
      operation_type: "capture",
      match_status: "UNMATCHED",
      rule: "strong_ref_linked",
      discrepancy_types: ["AMOUNT_MISMATCH"],
      left_ids: [1],
      right_ids: [2],
      amount_difference_minor: -100,
      score: null,
      alternatives: [],
      explanation: "shared reference with differences",
    };
    render(<ResultsTable rows={[row]} onSelect={onSelect} />);
    await user.tab();
    expect(screen.getByRole("button", { name: "Ver detalle de pay-0042" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith(row);
  });
});

describe("errors and session", () => {
  it("explains policy refusals without leaking internals", () => {
    expect(explain(403, { code: "segregation_of_duties" }).message).toMatch(/propusiste/);
    expect(explain(409, { code: "recommendation_obsolete" }).message).toMatch(/run más nuevo/);
    expect(explain(409, { code: "version_conflict" }).message).toMatch(/recargá/);
    expect(explain(500, "Traceback ... SELECT").message).toBe("Error 500.");
    expect(explain(503, { code: "ai_disabled" }).message).toMatch(/kill switch/);
  });

  it("decodes the dev token only for display", () => {
    const payload = btoa(JSON.stringify({ sub: "ana", roles: ["analyst"], tenant_id: "t", exp: 1 }))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    expect(decode(`h.${payload}.s`)).toMatchObject({ subject: "ana", roles: ["analyst"], tenant: "t" });
    expect(decode("not-a-token")).toBeNull();
  });
});
