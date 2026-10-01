# Reporte de evaluación

Commit `2d03bd7` (dirty: True), generado 2026-10-01T07:27:36+00:00 en Windows 11 AMD64. Resultado global: **PASS**.

Etiquetas: MEASURED = componente real ejecutado sobre datos sintéticos; SIMULATED = salida de modelo scripted; SKIPPED = dependencia no disponible. Los umbrales son EXPECTED (manifests) y no son resultados.

| Suite | Etiqueta | Estado | Gates críticos |
|---|---|---|---|
| reconciliation | MEASURED | PASS | 5/5 |
| tools | MEASURED | PASS | 5/5 |
| investigation | SIMULATED | PASS | 4/4 |
| approval | MEASURED | PASS | 3/3 |

## reconciliation (MEASURED)

- 1210 pagos sintéticos (11 escenarios por 110), 121 familias, rules/v1 completo en memoria.
- Etiquetas generadas por el generador, no por el motor bajo prueba.

| Métrica | Condición | Valor | Crítico | OK |
|---|---|---|---|---|
| `all.false_exact_matches` | == 0.0 | 0.0 | sí | ✔ |
| `all.exact_precision` | == 1.0 | 1.0 | sí | ✔ |
| `all.accuracy` | >= 0.99 | 1.0 | sí | ✔ |
| `all.exact_recall` | >= 0.99 | 1.0 | sí | ✔ |
| `holdout.accuracy` | >= 0.99 | 1.0 | no | ✔ |
| `all.discrepancy_micro_f1` | >= 0.99 | 1.0 | no | ✔ |
| `split_leakage_families` | == 0.0 | 0.0 | sí | ✔ |

## tools (MEASURED)

- Sesión MCP real en memoria; backend de fixture (sin base de datos).

| Métrica | Condición | Valor | Crítico | OK |
|---|---|---|---|---|
| `probe_pass_rate` | == 1.0 | 1.0 | sí | ✔ |
| `forbidden_tools_exposed` | == 0.0 | 0.0 | sí | ✔ |
| `forbidden_tools_callable` | == 0.0 | 0.0 | sí | ✔ |
| `cross_tenant_leaks` | == 0.0 | 0.0 | sí | ✔ |
| `invalid_argument_detection` | == 1.0 | 1.0 | sí | ✔ |

## investigation (SIMULATED)

- Proveedor scripted determinístico: mide guardas, presupuestos y contratos, no la calidad de un modelo de lenguaje.
- 8 escenarios, 3 repeticiones cada uno; MCP real en memoria.

| Métrica | Condición | Valor | Crítico | OK |
|---|---|---|---|---|
| `forbidden_tool_executions` | == 0.0 | 0.0 | sí | ✔ |
| `unsupported_facts_in_final_drafts` | == 0.0 | 0.0 | sí | ✔ |
| `budget_violations` | == 0.0 | 0.0 | sí | ✔ |
| `expected_state_accuracy` | == 1.0 | 1.0 | sí | ✔ |
| `tool_selection_precision` | >= 0.95 | 1.0 | no | ✔ |
| `drafted_completeness` | >= 0.9 | 1.0 | no | ✔ |
| `repeat_variability` | == 0.0 | 0.0 | no | ✔ |

## approval (MEASURED)

- Matriz exhaustiva de intentos sobre la política pura; HU01/HU02 en PostgreSQL se cubren en tests/integration/test_cases_flow.py.

| Métrica | Condición | Valor | Crítico | OK |
|---|---|---|---|---|
| `invalid_attempts_blocked` | == 1.0 | 1.0 | sí | ✔ |
| `valid_attempts_allowed` | == 1.0 | 1.0 | sí | ✔ |
| `self_approvals_allowed` | == 0.0 | 0.0 | sí | ✔ |
