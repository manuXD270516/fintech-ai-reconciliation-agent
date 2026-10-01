import { useEffect, useState } from "react";

import { decode, getToken, setToken } from "./auth";
import {
  AuditView,
  BatchView,
  BatchesView,
  CaseView,
  CasesView,
  InvestigationView,
  LoginView,
  RunView,
} from "./views";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash || "#/batches");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/batches");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export function App() {
  const [token, setTokenState] = useState(getToken());
  const session = decode(token);
  const hash = useHash();
  const [path = "", query = ""] = hash.slice(1).split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const params = new URLSearchParams(query);

  function logout() {
    setToken(null);
    setTokenState(null);
  }

  let view;
  if (!session) {
    view = <LoginView onLogin={() => setTokenState(getToken())} />;
  } else if (parts[0] === "batches" && parts[1]) {
    view = <BatchView batchId={parts[1]} />;
  } else if (parts[0] === "runs" && parts[1]) {
    view = <RunView runId={parts[1]} session={session} />;
  } else if (parts[0] === "investigations" && parts[1]) {
    view = <InvestigationView id={parts[1]} session={session} />;
  } else if (parts[0] === "cases" && parts[1] && parts[2] === "audit") {
    view = <AuditView id={parts[1]} />;
  } else if (parts[0] === "cases" && parts[1]) {
    view = <CaseView id={parts[1]} investigationId={params.get("inv")} session={session} />;
  } else if (parts[0] === "cases") {
    view = <CasesView />;
  } else {
    view = <BatchesView />;
  }

  return (
    <>
      <a className="skip-link" href="#main">
        Saltar al contenido
      </a>
      <header>
        <h1>Conciliación · panel de investigación</h1>
        <p className="muted">Datos sintéticos. Ninguna acción de este panel mueve dinero.</p>
        {session ? (
          <nav aria-label="Principal">
            <a href="#/batches">Lotes</a>
            <a href="#/cases">Casos</a>
            <span className="session">
              {session.subject} · {session.roles.join(", ")} · {session.tenant}
            </span>
            <button type="button" onClick={logout}>
              Cerrar sesión
            </button>
          </nav>
        ) : null}
      </header>
      <main id="main" tabIndex={-1}>
        {view}
      </main>
    </>
  );
}
