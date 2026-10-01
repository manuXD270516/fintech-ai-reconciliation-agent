# Estrategia de pruebas — M7

Unitarias del framework (estadística, splits, gates, regresiones, etiquetas) incluida una inyección de fallo crítico; ejecución real del paso `evals` en el gate; suite con base de datos en el smoke.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Estadística y splits | Split determinístico ≈60/20/20 sobre 3000 familias; Wilson, ratio, F1 y macro con N/A ante denominador cero (`tests/unit/test_evals.py`) |
| T02 | Gates y reportes | Gate crítico fallido → suite y reporte FAIL; no crítico no bloquea; SKIPPED sin métricas; Markdown con resultado global (mismo archivo) |
| T03 | Regresiones | Dirección `>=`/`<=`/`==` y tolerancia 0.02 (mismo archivo) |
| T04 | Bloqueo | `python -m recon_evals gate` con suites que violan un gate crítico termina con código 1 y reporte FAIL (mismo archivo) |
| T05 | Suites offline | Conciliación sin fuga de familias y con hash de dataset; matriz de aprobación; manifests completos; baseline versionado PASS con investigación SIMULATED (mismo archivo); paso `evals` del gate con 4 suites PASS |
| T06 | Suite con base de datos | Smoke `M7-T06`: `recon_evals run --suite retrieval` en el contenedor, etiqueta MEASURED, gates críticos de ACL y fuga en PASS, reporte guardado |
| T07 | Paridad y gate | `test_ci_parity.py` (el paso `evals` está en `ci.yml` en el mismo orden) y `scripts/gate.py all` |

## Ejecución y evidencias

`uv run python scripts/gate.py all` (incluye `evals` y el smoke). Evidencia en [evidence/](evidence/README.md).

## Stop condition

M7 no agrega suites con modelos reales ni jueces LLM.
