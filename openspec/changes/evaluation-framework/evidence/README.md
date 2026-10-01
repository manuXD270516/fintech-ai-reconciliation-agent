# Evidencia — evaluation-framework (M7)

Ejecutada el 2026-10-01 en Windows 11 (Docker 29.8.1, Compose 5.5.1, linux/amd64), rama `m7-evaluation-framework` con cambios sin commitear (los reportes registran `commit 2d03bd7`, `dirty: true`). Datos sintéticos; sin modelos reales. CI remoto no ejecutado (AC06 de M0).

Archivos:

- [gate-all.log](gate-all.log): `uv run python scripts/gate.py all` con el nuevo paso `evals`, todos PASS; 244 tests unitarios; smoke 18/18.
- [unit-tests.log](unit-tests.log): `pytest -v tests/unit/test_evals.py` (9 passed).
- [eval-offline-report.json](eval-offline-report.json) / [.md](eval-offline-report.md): reporte del paso `evals` (4 suites offline).
- [eval-db-suites.json](eval-db-suites.json): suite `retrieval` corrida con el mismo runner dentro de la red Compose (paso smoke `M7-T06`).
- [smoke.json](smoke.json): reporte del smoke.

## T01

`test_family_split_is_deterministic_and_roughly_60_20_20` y `test_statistics_report_na_instead_of_success_on_empty_denominators`. Ver [unit-tests.log](unit-tests.log).

## T02

`test_critical_gate_failure_blocks_and_non_critical_does_not` (FAIL por gate crítico, no crítico no bloquea, SKIPPED sin métricas, Markdown con resultado global). Ver [unit-tests.log](unit-tests.log).

## T03

`test_regressions_follow_gate_direction_and_tolerance` (`>=` con tolerancia 0.02, `==` estricto, `<=`). Ver [unit-tests.log](unit-tests.log).

## T04

`test_gate_command_fails_when_a_critical_gate_fails`: con suites que violan un gate crítico, `python -m recon_evals gate` devuelve 1 y el reporte queda FAIL. Ver [unit-tests.log](unit-tests.log).

## T05

[eval-offline-report.json](eval-offline-report.json) (2.48 s):

| Suite | Etiqueta | Resultado (MEASURED salvo indicación) |
|---|---|---|
| reconciliation | MEASURED | 1210 pagos, 121 familias, 0 familias filtradas; accuracy 1.0 en dev (n=750, IC 0.9949–1), calibration (n=180, IC 0.9791–1), holdout (n=280, IC 0.9865–1) y total (n=1210, IC 0.9968–1); precision y recall de EXACT 1.0; 0 falsos EXACT; macro-F1 y F1 de discrepancias 1.0 |
| tools | MEASURED | 4/4 probes (catálogo exacto, anotaciones de sólo lectura, registro propio legible, otro tenant `NOT_FOUND`); 0 tools prohibidas expuestas o invocables; 5/5 argumentos inválidos detectados |
| investigation | **SIMULATED** | 8 escenarios × 3: estados esperados 8/8, precisión de selección de tools 1.0, 0 tools prohibidas ejecutadas (11 pasos del modelo rechazados por política), 0 hechos sin soporte en borradores finales, 0 violaciones de presupuesto, completitud 1.0, variabilidad 0 (proveedor determinístico), ~15.6k tokens estimados en total |
| approval | MEASURED | 576 intentos (2 válidos, 574 inválidos): 100 % de inválidos bloqueados, 100 % de válidos permitidos, 0 autoaprobaciones |

Lectura honesta: la conciliación perfecta indica que el motor reproduce las etiquetas del generador sintético; ambos comparten el modelo del dominio y no prueba generalización a datos reales. La suite de investigación mide guardas y contratos con un proveedor scripted, no calidad de un LLM. Además, `test_reconciliation_suite_has_no_split_leakage_and_independent_labels`, `test_approval_matrix_and_manifests_are_consistent` y `test_committed_baseline_is_a_passing_offline_report` en [unit-tests.log](unit-tests.log).

## T06

[eval-db-suites.json](eval-db-suites.json) (paso `M7-T06`, MEASURED, PostgreSQL + pgvector reales): gates críticos en PASS (0 violaciones de ACL en los tres modos, 0 familias filtradas). Gates no críticos: recall@5 de holdout híbrido 0.9231 (≥ 0.85, cumple), precision@5 0.2308 (< 0.80, **no cumple**) y abstención en queries sin respuesta 0.5 (< 0.95, **no cumple**): se reportan como fallas no bloqueantes, coherentes con la evidencia de M3.

## T07

`test_ci_parity.py` en [gate-all.log](gate-all.log) (el paso `evals` está en `ci.yml` en el mismo orden que en `scripts/gate.py`) y el gate completo verde.
