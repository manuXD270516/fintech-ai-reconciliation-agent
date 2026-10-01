## Context

Unifica la evaluación incremental de M1–M6 según [docs/07-evals.md](../../../docs/07-evals.md) y las decisiones de [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md).

## Goals / Non-Goals

**Goals:** un comando, etiquetas honestas, splits sin fuga, gates críticos que bloquean, regresiones visibles.

**Non-Goals:** calidad de modelos reales, LLM-as-judge, adjudicación humana.

## Decisions

- **Manifests dentro del paquete.** La imagen instala el workspace de forma no editable; por eso los manifests viven en `recon_evals/manifests/` y viajan con el paquete. La raíz de datos se toma del directorio de trabajo (`RECON_REPO_ROOT` opcional): el gate corre desde la raíz del repo y el smoke desde `/app`.
- **Gates en los manifests.** `apply_gates` evalúa `metric op threshold` con rutas punteadas; criticidad explícita. `overall` es FAIL sólo por gates críticos.
- **Suites offline vs DB.** El paso `evals` corre `reconciliation`, `tools`, `investigation` y `approval` (≈5 s). `retrieval` necesita PostgreSQL + pgvector y corre en el smoke (`M7-T06`) con el mismo runner; fuera de él es SKIPPED.
- **Conciliación.** Dataset v2 regenerado con semilla 20261001 y 110 pagos por escenario (1210). Familia = escenario + bloque de 10 pagos; split por `sha256(familia) mod 100`. Las etiquetas vienen del generador, no de `rules/v1`; el runner sólo usa `labels.csv` para puntuar y para derivar el alcance de los lotes (tenant/proveedor/cuenta), nunca resultados.
- **Investigación (SIMULATED).** 8 escenarios (fiel, exacto, alucinación, inyección, timeouts, planificador sin fin, salida malformada, revisor que rechaza) × 3 repeticiones sobre una sesión MCP real en memoria; mide guardas y presupuestos, y la variabilidad entre repeticiones (0 por construcción con el scripted; con un modelo real será distinta).
- **Aprobación.** Producto cartesiano de 576 intentos contra un oráculo escrito de forma independiente (re-enunciado de las reglas). HU01/HU02 sobre PostgreSQL siguen en los tests de integración de M6.
- **Regresiones.** Comparación por clave `suite:métrica` con la dirección del gate y tolerancia 0.02 (igualdad estricta para `==`). El baseline `evals/baselines/offline.json` se versiona; actualizarlo es un cambio revisable.

## Risks / Trade-offs

- Resultados perfectos en conciliación reflejan que generador y reglas comparten el mismo modelo del dominio; no prueban generalización a datos reales (se declara en el reporte).
- El oráculo de aprobación re-enuncia la política; detecta regresiones de implementación, no errores de la política misma.
- Los gates no críticos de retrieval fallan hoy (precision@5 y abstención por debajo de lo EXPECTED); se reportan como tales.
