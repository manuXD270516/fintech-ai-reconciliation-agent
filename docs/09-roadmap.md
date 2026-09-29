# Roadmap M0–M10

Secuencia basada en dependencias y evidencia, sin fechas ficticias. Estado de todos los milestones funcionales: **pendientes**. Este trabajo entrega el diseño y el change propuesto de M0, no M0 implementado.

| Milestone | Alcance y entregable | Dependencias | Criterio de salida / demostración |
|---|---|---|---|
| M0 — Repository bootstrap | Estructura, entorno reproducible, API health, PostgreSQL/pgvector, NATS, CI base y guía sintética | Diseño y change actual | Clone limpio instala lockfiles, levanta infra/API y pasa liveness/readiness, smoke, lint/type y validación de spec; sin lógica de pagos |
| M1 — Transaction domain model | Money, observations, batches, revisiones, mapeos y fixtures | M0 | Dinero exacto, scope, idempotencia y timestamps con pruebas de propiedades/negativos; datos versionados |
| M2 — Deterministic reconciliation engine | Ingestion sintética CSV/API/eventos, normalización, snapshots, reglas 1:1, outbox/inbox y discrepancies | M1 | Casos exactos/ambiguos/faltantes/duplicados/mismatches/errores; replay/out-of-order correctos; cero LLM en exactos |
| M3 — RAG knowledge base | Corpus, chunking, metadata, embeddings, FTS+vector, RRF y citas | M0; conceptos de M1 | Baselines lexical/vector/híbrido, precision/recall, abstención y ACL medidos con corpus sintético |
| M4 — MCP server | Seis READ TOOLS, schemas, scopes, timeouts y auditoría | M2 + M3 | Discovery/contratos/transportes verificados; cross-tenant y write attempts denegados |
| M5 — Investigation Agent | Routing, planner/executor, evidence phase, budgets y abstención | M4 | Evidencia separada; tool evals; borradores sin efecto operativo; tests de fallas e injection |
| M6 — Reviewer + Human approval | Revisión de conclusiones, recomendaciones, RBAC, versionado y aprobación API | M5 | Sin autoaprobación; conflicto de versión y concurrencia cubiertos; audit reconstructible |
| M7 — Evaluation framework | Runner y manifests comunes, splits, reportes y regresiones | Métricas incrementales M1–M6 | Suites reproducibles y resultados etiquetados; gates críticos bloquean release; sin leakage |
| M8 — React investigation dashboard | Batches, discrepancias, timeline, citas, tres categorías de claims, decisiones | M6 + contratos/reportes M7 | Flujo analista→supervisor probado E2E; visibilidad de vigencia, errores, accesibilidad por teclado |
| M9 — Observability and security | OpenTelemetry, dashboards, runbooks, fault injection, hardening y restore | M2–M8 | Replay/restore demostrados, auth/ACL revisadas, secretos escaneados y alertas verificadas |
| M10 — Public demo | Publicación del repositorio/demo, walkthrough, dataset y reporte sanitizado | Gates M0–M9 | Demo sintética reproducible, limitaciones visibles, evidencias públicas, costos acotados y aprobación humana funcional |

## Dos puntos de entrega

**MVP técnico (M0–M6):** importar fuentes sintéticas, reconciliar determinísticamente, investigar una excepción con RAG/MCP y registrar aprobación humana por API. Incluye evals específicas de cada módulo desde su introducción; M7 no es permiso para desarrollar agentes sin evaluarlos.

**Demo pública (M7–M10):** framework unificado, UI y evidencia observable de calidad/seguridad. No afirmar “production ready”, capacidad bancaria real ni rendimiento productivo a partir de esta demo.

## Política de changes OpenSpec

Primer change: `bootstrap-mvp-foundation`, acotado a M0. Próximos nombres orientativos: `transaction-domain`, `deterministic-reconciliation`, `hybrid-knowledge-retrieval`, `read-only-mcp`, `bounded-investigation`, `review-and-human-approval`, `evaluation-framework`, `investigation-dashboard`, `observability-security`, `public-demo`.

Antes de cada implementación sustancial: proposal, requirements con escenarios, acceptance criteria, design, tasks y test strategy. Cambios en reglas de matching, permisos, tools, prompting o métricas también son cambios de comportamiento. No basta con actualizar un prompt fuera de spec. Revisión de diseño resuelve decisiones que alteren alcance; validación OpenSpec revisa estructura, no prueba corrección del sistema.

Cada task se marca completada sólo con evidencia. Al finalizar implementación y verificación, archivar change e integrar sus delta specs en `openspec/specs/`. No copiar specs propuestas como comportamiento vigente antes de tiempo.
