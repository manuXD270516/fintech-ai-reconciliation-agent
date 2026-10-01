# Criterios de aceptación — evaluation-framework

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/evaluation-framework/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Un runner y manifests versionados por suite con dataset, origen, split, etiquetas y gates | RF-01 | T02, T05 | 1.1 | PASS | [T02](evidence/README.md#t02), [T05](evidence/README.md#t05) |
| AC02 | Etiquetas MEASURED/SIMULATED/SKIPPED, umbrales como EXPECTED, N/A ante denominador cero, n e IC Wilson | RF-02 | T01, T02, T05 | 1.1 | PASS | [T01](evidence/README.md#t01), [T02](evidence/README.md#t02), [T05](evidence/README.md#t05) |
| AC03 | Splits por familia sin fuga y gold independiente del componente evaluado | RF-03 | T01, T05 | 1.1 | PASS | [T01](evidence/README.md#t01), [T05](evidence/README.md#t05) |
| AC04 | Cinco suites (conciliación, retrieval, tools, investigación, aprobación) con sus métricas | RF-04 | T05, T06 | 2.1, 2.2 | PASS | [T05](evidence/README.md#t05), [T06](evidence/README.md#t06) |
| AC05 | Un gate crítico fallido bloquea el paso `evals` (código distinto de cero) | RF-05 | T02, T04 | 1.2 | PASS | [T02](evidence/README.md#t02), [T04](evidence/README.md#t04) |
| AC06 | Regresiones frente al baseline versionado detectadas con dirección y tolerancia | RF-06 | T03, T04 | 1.2 | PASS | [T03](evidence/README.md#t03), [T04](evidence/README.md#t04) |
| AC07 | Reportes reproducibles con commit, dirty, host, tiempos, manifests con hash, métricas, gates y fallos | RF-07 | T02, T05 | 1.1 | PASS | [T02](evidence/README.md#t02), [T05](evidence/README.md#t05), [reporte](evidence/eval-offline-report.json) |
| AC08 | Paso `evals` en gate y CI con paridad exacta; gate completo verde | RF-05 | T07 | 3.1 | PASS | [T07](evidence/README.md#t07), [gate](evidence/gate-all.log) |

Definition of Done de M7: AC01–AC08 en PASS con evidencia. Ninguna métrica de calidad de un modelo real se reporta (no hay suite con modelo real en gates). El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
