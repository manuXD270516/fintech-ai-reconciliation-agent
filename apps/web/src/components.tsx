import { type FormEvent, type ReactNode, useId, useState } from "react";

export function StatusBadge({ value }: { value: string }) {
  return <span className={`badge badge-${value.toLowerCase().replace(/_/g, "-")}`}>{value}</span>;
}

export function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="banner banner-error">
      {error}
    </p>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="panel">
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

export interface Claim {
  claim_id: string;
  kind: string;
  statement: string;
  evidence_refs: string[];
  limitations: string;
  needed_evidence?: string | null;
}

export interface Citation {
  ref: string;
  provenance: Record<string, unknown>;
}

const KIND_TITLES: Record<string, string> = {
  FACT: "Hechos (FACT)",
  INFERENCE: "Inferencias (INFERENCE)",
  HYPOTHESIS: "Hipótesis (HYPOTHESIS)",
};

function describe(citation: Citation | undefined): string {
  if (!citation) return "cita no resuelta";
  const p = citation.provenance;
  const where = String(p.locator ?? p.source_id ?? "registro calculado");
  const when = p.effective_at ? ` · vigente desde ${String(p.effective_at)}` : "";
  return `${where}${when}`;
}

export function ClaimGroup({
  kind,
  claims,
  citations,
}: {
  kind: "FACT" | "INFERENCE" | "HYPOTHESIS";
  claims: Claim[];
  citations: Citation[];
}) {
  const byRef = new Map(citations.map((c) => [c.ref, c]));
  return (
    <Section title={KIND_TITLES[kind] ?? kind}>
      {claims.length === 0 ? (
        <p className="muted">Sin afirmaciones de este tipo.</p>
      ) : (
        <ul className="claims">
          {claims.map((claim) => (
            <li key={claim.claim_id} className={`claim claim-${kind.toLowerCase()}`}>
              <p>{claim.statement}</p>
              {claim.limitations ? <p className="muted">Límite: {claim.limitations}</p> : null}
              {claim.needed_evidence ? (
                <p className="muted">Evidencia necesaria: {claim.needed_evidence}</p>
              ) : null}
              <ul className="refs" aria-label="Citas">
                {claim.evidence_refs.map((ref) => (
                  <li key={ref}>
                    <code>{ref}</code> — {describe(byRef.get(ref))}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export const DECISION_EFFECT =
  "Registrar la decisión cambia el estado del caso y queda auditado; no ejecuta reembolsos, " +
  "ajustes ni movimientos de dinero.";

export interface DecisionInput {
  decision: "APPROVE" | "REJECT" | "NEEDS_INFORMATION";
  reason: string;
  expected_version: number;
  idempotency_key: string;
}

export function DecisionForm({
  caseVersion,
  runIsLatest,
  onSubmit,
}: {
  caseVersion: number;
  runIsLatest: boolean;
  onSubmit: (input: DecisionInput) => Promise<void> | void;
}) {
  const [decision, setDecision] = useState<DecisionInput["decision"]>("APPROVE");
  const [reason, setReason] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);
  const [key] = useState(() => `web-${crypto.randomUUID()}`);
  const reasonId = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (reason.trim().length < 10) {
      setInvalid("El motivo es obligatorio (mínimo 10 caracteres).");
      return;
    }
    setInvalid(null);
    await onSubmit({ decision, reason: reason.trim(), expected_version: caseVersion, idempotency_key: key });
  }

  return (
    <form onSubmit={submit} className="panel" aria-label="Decisión humana">
      <fieldset disabled={!runIsLatest}>
        <legend>Decisión sobre la versión {caseVersion}</legend>
        {!runIsLatest ? (
          <p className="banner banner-warning">
            Existe un run más nuevo del lote: esta recomendación no es aprobable.
          </p>
        ) : null}
        {(["APPROVE", "REJECT", "NEEDS_INFORMATION"] as const).map((value) => (
          <label key={value} className="radio">
            <input
              type="radio"
              name="decision"
              value={value}
              checked={decision === value}
              onChange={() => setDecision(value)}
            />
            {{ APPROVE: "Aprobar", REJECT: "Rechazar", NEEDS_INFORMATION: "Pedir información" }[value]}
          </label>
        ))}
        <label htmlFor={reasonId}>Motivo (obligatorio)</label>
        <textarea
          id={reasonId}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          aria-invalid={invalid ? true : undefined}
        />
        {invalid ? <p role="alert" className="field-error">{invalid}</p> : null}
        <p className="effect">{DECISION_EFFECT}</p>
        <button type="submit">Registrar decisión</button>
      </fieldset>
    </form>
  );
}
