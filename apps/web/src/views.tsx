import { type FormEvent, useCallback, useEffect, useState } from "react";

import {
  type AuditTrail,
  type CaseOut,
  type Investigation,
  type ResultRow,
  api,
  unwrap,
} from "./api/client";
import { type Session, hasRole, setToken } from "./auth";
import { DEMO_MODE, demoToken, loadFixture } from "./demo";
import {
  type Citation,
  type Claim,
  ClaimGroup,
  DecisionForm,
  type DecisionInput,
  ErrorBanner,
  Section,
  StatusBadge,
} from "./components";

const TERMINAL = new Set(["NOT_NEEDED", "DRAFTED", "ABSTAINED", "ESCALATED", "FAILED"]);

function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    load()
      .then((value) => {
        setData(value);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(reload, [reload]);
  return { data, error, reload, setError };
}

const DEMO_ROLES: [string, string][] = [
  ["analyst", "Analista"],
  ["supervisor", "Supervisora"],
  ["auditor", "Auditor"],
];

function DemoLoginView({ onLogin }: { onLogin: () => void }) {
  async function enter(role: string) {
    const data = await loadFixture();
    setToken(demoToken(role, data.subjects[role] ?? role, data.tenant));
    onLogin();
  }
  return (
    <section className="panel" aria-labelledby="demo-login">
      <h2 id="demo-login">Demo estática (sólo lectura)</h2>
      <p>
        Datos sintéticos capturados de una ejecución real del stack local: lotes, resultados, una
        investigación con borrador <strong>SIMULATED</strong>, un caso con su decisión humana y la
        auditoría. No hay backend: las acciones que modifican datos se rechazan. El flujo completo
        corre en local siguiendo el{" "}
        <a href="https://github.com/manuXD270516/fintech-ai-reconciliation-agent/blob/main/docs/demo/walkthrough.md">
          walkthrough
        </a>
        .
      </p>
      <div className="actions">
        {DEMO_ROLES.map(([role, label]) => (
          <button key={role} type="button" onClick={() => void enter(role)}>
            Entrar como {label}
          </button>
        ))}
      </div>
    </section>
  );
}

export function LoginView({ onLogin }: { onLogin: () => void }) {
  if (DEMO_MODE) return <DemoLoginView onLogin={onLogin} />;
  return <TokenLoginView onLogin={onLogin} />;
}

function TokenLoginView({ onLogin }: { onLogin: () => void }) {
  const [token, setValue] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    setToken(token);
    onLogin();
  }
  return (
    <form onSubmit={submit} className="panel" aria-label="Iniciar sesión">
      <h2>Sesión de desarrollo</h2>
      <p>
        Pegá un token generado con{" "}
        <code>uv run python scripts/dev_auth.py token --sub ana --role analyst</code>. Sólo para
        uso local (loopback).
      </p>
      <label htmlFor="token">Token JWT</label>
      <textarea id="token" value={token} onChange={(e) => setValue(e.target.value)} rows={4} />
      <button type="submit">Usar token</button>
    </form>
  );
}

export function BatchesView() {
  const { data, error } = useLoad(async () => unwrap(await api.GET("/v1/batches")), []);
  return (
    <Section title="Lotes">
      <ErrorBanner error={error} />
      <table>
        <caption className="sr-only">Lotes de conciliación</caption>
        <thead>
          <tr>
            <th scope="col">Lote</th>
            <th scope="col">Proveedor</th>
            <th scope="col">Cuenta</th>
            <th scope="col">Moneda</th>
            <th scope="col">Completitud</th>
            <th scope="col">Versión</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((b) => (
            <tr key={b.batch_id}>
              <td>
                <a href={`#/batches/${encodeURIComponent(b.batch_id)}`}>{b.batch_id}</a>
              </td>
              <td>{b.provider_id}</td>
              <td>{b.merchant_account}</td>
              <td>{b.currency}</td>
              <td>
                {b.left_complete && b.right_complete ? "fuentes completas" : "fuentes incompletas"}
              </td>
              <td>{b.version}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

export function BatchView({ batchId }: { batchId: string }) {
  const { data, error } = useLoad(
    async () =>
      unwrap(await api.GET("/v1/batches/{batch_id}/runs", { params: { path: { batch_id: batchId } } })),
    [batchId],
  );
  return (
    <Section title={`Runs del lote ${batchId}`}>
      <ErrorBanner error={error} />
      <ol className="runs">
        {(data ?? []).map((r) => (
          <li key={r.run_id}>
            <a href={`#/runs/${r.run_id}`}>
              Run {r.run_number} · {r.status} · {r.ruleset_version}
            </a>{" "}
            <span className="muted">snapshot {r.snapshot_hash?.slice(0, 12) ?? "—"}</span>
          </li>
        ))}
      </ol>
    </Section>
  );
}

export function ResultsTable({
  rows,
  onSelect,
}: {
  rows: ResultRow[];
  onSelect: (row: ResultRow) => void;
}) {
  return (
    <table>
      <caption className="sr-only">Resultados del run</caption>
      <thead>
        <tr>
          <th scope="col">Referencia</th>
          <th scope="col">Resultado</th>
          <th scope="col">Discrepancias</th>
          <th scope="col">Diferencia</th>
          <th scope="col">Regla</th>
          <th scope="col">
            <span className="sr-only">Acciones</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.ordinal}>
            <td>{row.payment_ref}</td>
            <td>
              <StatusBadge value={row.match_status} />
            </td>
            <td>{row.discrepancy_types.join(", ") || "—"}</td>
            <td>{row.amount_difference_minor ?? "—"}</td>
            <td>{row.rule}</td>
            <td>
              <button type="button" onClick={() => onSelect(row)}>
                Ver detalle de {row.payment_ref}
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RunView({ runId, session }: { runId: string; session: Session | null }) {
  const [filter, setFilter] = useState<string>("");
  const [selected, setSelected] = useState<ResultRow | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const run = useLoad(
    async () => unwrap(await api.GET("/v1/runs/{run_id}", { params: { path: { run_id: runId } } })),
    [runId],
  );
  const results = useLoad(async () => {
    type MatchStatus = "EXACT" | "PROBABLE" | "UNMATCHED" | "NOT_EVALUATED";
    const query = { limit: 500, ...(filter ? { match_status: filter as MatchStatus } : {}) };
    return unwrap(
      await api.GET("/v1/runs/{run_id}/results", { params: { path: { run_id: runId }, query } }),
    );
  }, [runId, filter]);

  async function investigate(row: ResultRow) {
    try {
      const out = unwrap(
        await api.POST("/v1/runs/{run_id}/results/{ordinal}/investigations", {
          params: { path: { run_id: runId, ordinal: row.ordinal } },
        }),
      );
      window.location.hash = `#/investigations/${out.investigation_id}`;
    } catch (err) {
      setActionError((err as Error).message);
    }
  }

  async function openCase(row: ResultRow) {
    try {
      const out = unwrap(
        await api.POST("/v1/runs/{run_id}/results/{ordinal}/cases", {
          params: { path: { run_id: runId, ordinal: row.ordinal } },
        }),
      );
      window.location.hash = `#/cases/${out.case_id}`;
    } catch (err) {
      setActionError((err as Error).message);
    }
  }

  const analyst = hasRole(session, "analyst");
  return (
    <>
      <Section title={`Run ${run.data?.run_number ?? ""}`}>
        <ErrorBanner error={run.error} />
        {run.data ? (
          <p>
            Lote <a href={`#/batches/${run.data.batch_id}`}>{run.data.batch_id}</a> · {run.data.status} ·
            ruleset {run.data.ruleset_version} · snapshot <code>{run.data.snapshot_hash?.slice(0, 16)}</code>{" "}
            · conteos: {Object.entries(run.data.counts).map(([k, v]) => `${k} ${v}`).join(", ")}
          </p>
        ) : null}
        <label htmlFor="status-filter">Filtrar por resultado</label>
        <select id="status-filter" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">Todos</option>
          {["EXACT", "PROBABLE", "UNMATCHED", "NOT_EVALUATED"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <ErrorBanner error={results.error} />
        <ResultsTable rows={results.data?.items ?? []} onSelect={setSelected} />
      </Section>
      {selected ? (
        <Section title={`Detalle de ${selected.payment_ref}`}>
          <p>{selected.explanation}</p>
          {selected.score !== null && selected.score !== undefined ? (
            <p className="muted">Score de ranking {selected.score} (no es una probabilidad).</p>
          ) : null}
          <p className="muted">
            Ledger {selected.left_ids.join(", ") || "—"} · proveedor {selected.right_ids.join(", ") || "—"}
          </p>
          <ErrorBanner error={actionError} />
          {analyst ? (
            <div className="actions">
              <button type="button" onClick={() => void investigate(selected)}>
                Solicitar investigación
              </button>
              <button type="button" onClick={() => void openCase(selected)}>
                Abrir caso
              </button>
            </div>
          ) : (
            <p className="muted">Sólo un analista puede solicitar investigaciones o abrir casos.</p>
          )}
        </Section>
      ) : null}
    </>
  );
}

interface Draft {
  facts: Claim[];
  inferences: Claim[];
  hypotheses: Claim[];
  citations: Citation[];
  missing_evidence: string[];
  recommended_next_step: string;
  label: string;
  operational_effect: string;
  confidence_assessment: { calibration: string; evidence_coverage: number };
  review_result: { result: string; objections: { objection: string }[] } | null;
  untrusted_content_warnings: string[];
}

export function DraftView({ draft }: { draft: Draft }) {
  return (
    <>
      <p>
        <StatusBadge value={draft.label} /> Confianza <strong>{draft.confidence_assessment.calibration}</strong>{" "}
        (cobertura de evidencia {draft.confidence_assessment.evidence_coverage}) · efecto operativo:{" "}
        <strong>{draft.operational_effect}</strong>
      </p>
      {draft.untrusted_content_warnings.length ? (
        <p className="banner banner-warning">
          Hay fragmentos con instrucciones no confiables; se trataron sólo como datos.
        </p>
      ) : null}
      <ClaimGroup kind="FACT" claims={draft.facts} citations={draft.citations} />
      <ClaimGroup kind="INFERENCE" claims={draft.inferences} citations={draft.citations} />
      <ClaimGroup kind="HYPOTHESIS" claims={draft.hypotheses} citations={draft.citations} />
      <Section title="Evidencia faltante y siguiente paso">
        <ul>
          {draft.missing_evidence.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
        <p>
          Siguiente paso sugerido: <code>{draft.recommended_next_step}</code> (requiere decisión humana)
        </p>
      </Section>
      {draft.review_result ? (
        <Section title="Revisión independiente">
          <p>
            Resultado: <StatusBadge value={draft.review_result.result} /> (no es una aprobación humana)
          </p>
          <ul>
            {draft.review_result.objections.map((o) => (
              <li key={o.objection}>{o.objection}</li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  );
}

export function InvestigationView({ id, session }: { id: string; session: Session | null }) {
  const { data, error, reload } = useLoad(
    async () =>
      unwrap(
        await api.GET("/v1/investigations/{investigation_id}", {
          params: { path: { investigation_id: id } },
        }),
      ) as Investigation,
    [id],
  );
  const [caseError, setCaseError] = useState<string | null>(null);
  useEffect(() => {
    if (data && !TERMINAL.has(data.state)) {
      const timer = setTimeout(reload, 1000);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [data, reload]);
  const record = (data?.record ?? {}) as Record<string, unknown>;
  const steps = (record.steps ?? []) as { tool: string; ok: boolean; error_code: string | null; seconds: number }[];
  const budget = (record.budget ?? {}) as Record<string, number>;
  const draft = record.draft as Draft | null | undefined;

  async function openCase() {
    const [runId, ordinal] = (data?.case_ref ?? "").split("#");
    try {
      const out = unwrap(
        await api.POST("/v1/runs/{run_id}/results/{ordinal}/cases", {
          params: { path: { run_id: runId ?? "", ordinal: Number(ordinal) } },
        }),
      );
      window.location.hash = `#/cases/${out.case_id}?inv=${id}`;
    } catch (err) {
      setCaseError((err as Error).message);
    }
  }

  return (
    <>
      <Section title="Investigación">
        <ErrorBanner error={error} />
        {data ? (
          <p aria-live="polite">
            Estado <StatusBadge value={data.state} /> · caso <code>{data.case_ref}</code> · versión{" "}
            {data.case_version} · modelo <code>{String(record.model ?? "")}</code> · llamadas MCP{" "}
            {budget.tool_calls ?? 0}/{budget.max_tool_calls ?? 6} · generativas {budget.generative_calls ?? 0}/
            {budget.max_generative_calls ?? 4}
          </p>
        ) : null}
        <h3>Pasos (timeline)</h3>
        <ol className="timeline">
          {steps.map((s, i) => (
            <li key={`${s.tool}-${i}`}>
              <code>{s.tool}</code> · {s.ok ? "ok" : `error ${s.error_code}`} · {s.seconds}s
            </li>
          ))}
        </ol>
        {Array.isArray(record.issues) && record.issues.length ? (
          <ul className="muted">
            {(record.issues as string[]).map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        ) : null}
        {data && TERMINAL.has(data.state) && hasRole(session, "analyst") ? (
          <button type="button" onClick={() => void openCase()}>
            Abrir caso con este borrador
          </button>
        ) : null}
        <ErrorBanner error={caseError} />
      </Section>
      {draft ? <DraftView draft={draft} /> : null}
    </>
  );
}

const ACTIONS = [
  ["REQUEST_PROVIDER_INFO", "Pedir información al proveedor"],
  ["CLOSE_AS_EXPLAINED", "Cerrar como explicado"],
  ["ACCEPT_PROBABLE_MATCH", "Aceptar match probable"],
  ["REQUEST_ADJUSTMENT_REVIEW", "Pedir revisión de ajuste (sin ejecutarlo)"],
] as const;

export function CaseView({
  id,
  investigationId,
  session,
}: {
  id: string;
  investigationId: string | null;
  session: Session | null;
}) {
  const { data, error, reload, setError } = useLoad(
    async () => unwrap(await api.GET("/v1/cases/{case_id}", { params: { path: { case_id: id } } })) as CaseOut,
    [id],
  );
  const [action, setAction] = useState<(typeof ACTIONS)[number][0]>("REQUEST_PROVIDER_INFO");
  const [rationale, setRationale] = useState("");
  const [adopt, setAdopt] = useState(Boolean(investigationId));
  const [notice, setNotice] = useState<string | null>(null);

  async function propose(event: FormEvent) {
    event.preventDefault();
    if (!data) return;
    try {
      unwrap(
        await api.POST("/v1/cases/{case_id}/recommendations", {
          params: { path: { case_id: id } },
          body: {
            action,
            rationale,
            expected_version: data.version,
            investigation_id: adopt && investigationId ? investigationId : null,
          },
        }),
      );
      setNotice("Recomendación propuesta; queda pendiente de una decisión humana.");
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function decide(recommendationId: string, input: DecisionInput) {
    try {
      const out = unwrap(
        await api.POST("/v1/cases/{case_id}/decisions", {
          params: { path: { case_id: id } },
          body: { recommendation_id: recommendationId, ...input },
        }),
      );
      setNotice(`Decisión ${out.decision} registrada sobre la versión ${out.approved_version}. ${out.operational_effect}`);
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const pending = data?.recommendations.find((r) => r.status === "PENDING");
  const canPropose = data && ["OPEN", "REJECTED", "NEEDS_INFORMATION"].includes(data.status);
  return (
    <>
      <Section title="Caso">
        <ErrorBanner error={error} />
        {notice ? (
          <p role="status" className="banner banner-ok">
            {notice}
          </p>
        ) : null}
        {data ? (
          <>
            <p>
              Estado <StatusBadge value={data.status} /> · versión <strong>{data.version}</strong> · caso{" "}
              <code>{data.case_ref}</code>
            </p>
            <p className={data.run_is_latest ? "banner banner-ok" : "banner banner-warning"}>
              {data.run_is_latest
                ? "Vigente: el caso se basa en el run más reciente del lote."
                : "Obsoleto: existe un run más nuevo del lote; ninguna recomendación es aprobable."}
            </p>
            {hasRole(session, "auditor") || hasRole(session, "supervisor") ? (
              <p>
                <a href={`#/cases/${id}/audit`}>Ver traza de auditoría</a>
              </p>
            ) : null}
          </>
        ) : null}
      </Section>
      <Section title="Recomendaciones">
        <ul>
          {(data?.recommendations ?? []).map((r) => (
            <li key={r.id}>
              <StatusBadge value={r.status} /> {r.action} · propuesta por {r.proposer} · revisión{" "}
              {r.review_result} · {r.rationale}
              {Array.isArray(r.evidence.citations) ? (
                <span className="muted"> · {(r.evidence.citations as string[]).length} citas</span>
              ) : null}
            </li>
          ))}
        </ul>
      </Section>
      {canPropose && hasRole(session, "analyst") ? (
        <form onSubmit={propose} className="panel" aria-label="Proponer recomendación">
          <h2>Proponer recomendación</h2>
          <label htmlFor="action">Acción (ninguna mueve dinero)</label>
          <select id="action" value={action} onChange={(e) => setAction(e.target.value as typeof action)}>
            {ACTIONS.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
          <label htmlFor="rationale">Fundamento</label>
          <textarea id="rationale" value={rationale} onChange={(e) => setRationale(e.target.value)} rows={3} />
          {investigationId ? (
            <label className="checkbox">
              <input type="checkbox" checked={adopt} onChange={(e) => setAdopt(e.target.checked)} />
              Adoptar el borrador de investigación {investigationId.slice(0, 8)} (requiere revisión SUPPORTED)
            </label>
          ) : null}
          <button type="submit">Proponer</button>
        </form>
      ) : null}
      {pending && data && data.status === "HUMAN_REVIEW" && hasRole(session, "supervisor") ? (
        <DecisionForm
          caseVersion={data.version}
          runIsLatest={data.run_is_latest}
          onSubmit={(input) => decide(pending.id, input)}
        />
      ) : null}
    </>
  );
}

export function AuditView({ id }: { id: string }) {
  const { data, error } = useLoad(
    async () =>
      unwrap(await api.GET("/v1/cases/{case_id}/audit", { params: { path: { case_id: id } } })) as AuditTrail,
    [id],
  );
  return (
    <Section title="Traza de auditoría">
      <ErrorBanner error={error} />
      {data ? (
        <>
          <p>
            Ruleset <code>{String(data.rules.ruleset_version)}</code> · snapshot{" "}
            <code>{String(data.rules.snapshot_hash).slice(0, 16)}</code> · {data.investigations.length}{" "}
            investigación(es) · {data.decisions.length} decisión(es)
          </p>
          <table>
            <caption className="sr-only">Entradas de auditoría</caption>
            <thead>
              <tr>
                <th scope="col">Momento</th>
                <th scope="col">Actor</th>
                <th scope="col">Acción</th>
                <th scope="col">Resultado</th>
              </tr>
            </thead>
            <tbody>
              {data.audit.map((e) => (
                <tr key={e.id}>
                  <td>{e.occurred_at}</td>
                  <td>{e.actor}</td>
                  <td>{e.action}</td>
                  <td>{e.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </Section>
  );
}

export function CasesView() {
  const [status, setStatus] = useState("HUMAN_REVIEW");
  const { data, error } = useLoad(
    async () =>
      unwrap(
        await api.GET("/v1/cases", {
          params: { query: status ? { status: status as "HUMAN_REVIEW" } : {} },
        }),
      ),
    [status],
  );
  return (
    <Section title="Casos">
      <label htmlFor="case-status">Estado</label>
      <select id="case-status" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">Todos</option>
        {["OPEN", "HUMAN_REVIEW", "APPROVED", "REJECTED", "NEEDS_INFORMATION", "CLOSED"].map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <ErrorBanner error={error} />
      <ul>
        {(data ?? []).map((c) => (
          <li key={c.case_id}>
            <a href={`#/cases/${c.case_id}`}>{c.case_ref}</a> <StatusBadge value={c.status} /> v{c.version}
          </li>
        ))}
      </ul>
    </Section>
  );
}
