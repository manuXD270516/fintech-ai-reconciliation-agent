## Why

M2–M6 midieron cada módulo por separado con tests y reportes ad hoc. Para afirmar calidad (y sobre todo para no afirmar más de lo medido) hace falta un framework único: manifests versionados, splits sin fuga, métricas con denominadores e intervalos, etiquetas MEASURED/SIMULATED/SKIPPED, gates críticos que bloquean el gate de release y comparación contra un baseline para detectar regresiones.

## What Changes

- **Paquete `recon_evals`** (`evals/`) con un runner (`python -m recon_evals run|gate|compare`) y reportes JSON + Markdown con commit, estado del árbol, host, tiempos, configuración y hashes de datasets.
- **Manifests versionados** por suite (`recon_evals/manifests/*.json`): dataset, versión, semilla, origen, política de split, etiquetas, acciones prohibidas y gates (umbral, dirección, criticidad). Los umbrales son EXPECTED; nunca se reportan como resultados.
- **Suites:** `reconciliation` (1210 pagos sintéticos, 121 familias, accuracy, precision/recall de EXACT, F1 por clase y de discrepancias, matriz de confusión, IC Wilson), `retrieval` (requiere PostgreSQL; reutiliza la evaluación de M3), `tools` (contratos MCP en sesión real en memoria), `investigation` (SIMULATED: 8 escenarios × 3 repeticiones con guardas, presupuestos y completitud) y `approval` (matriz exhaustiva de 576 intentos contra un oráculo independiente).
- **Splits por familia** (sha256 de la familia → 60/20/20 dev/calibration/holdout) con chequeo de fuga.
- **Gate `evals`** en `scripts/gate.py` y en CI (paridad exacta): corre las suites offline, falla ante cualquier gate crítico o regresión frente a `evals/baselines/offline.json`. Las suites con base de datos corren en el smoke (`M7-T06`).

## Capabilities

### New Capabilities

- `evaluation-framework`: evaluación reproducible y etiquetada con manifests, splits sin fuga, gates críticos y regresiones.

### Modified Capabilities

Ninguna en specs vigentes; el gate de calidad agrega el paso `evals` (y `ci.yml` lo refleja).

## Impact

Nuevo miembro del workspace `evals` (en la imagen para el smoke), paso de gate y de CI, baseline versionado, `evals/reports/` ignorado por git.

Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md); diseño: [docs/07-evals.md](../../../docs/07-evals.md).

## Non-goals

Suite con modelo real (requiere Ollama y presupuesto explícito; no forma parte de gates), LLM-as-judge, adjudicación humana de errores, calibración de umbrales de confianza y benchmarks de rendimiento.
