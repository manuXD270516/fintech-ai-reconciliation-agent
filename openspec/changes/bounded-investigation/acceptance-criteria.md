# Criterios de aceptación — bounded-investigation

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/bounded-investigation/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Routing con motivo explícito; exactos/espera/faltantes sin modelo ni tools | RF-01 | T01, T08, T09 | 1.1 | PASS | [T01](evidence/README.md#t01), [T08](evidence/README.md#t08), [T09](evidence/README.md#t09) |
| AC02 | Pasos del modelo fuera de política rechazados y registrados; write tools e URLs nunca ejecutadas (AG02) | RF-02 | T02 | 1.1 | PASS | [T02](evidence/README.md#t02) |
| AC03 | Evidencia sólo por MCP con identidad fijada; errores como brechas explícitas | RF-03 | T05, T06, T08 | 1.2 | PASS | [T05](evidence/README.md#t05), [T06](evidence/README.md#t06), [T08](evidence/README.md#t08) |
| AC04 | Fase de evidencia: hechos calculados, FACT con registro y cifras soportadas, citas resolubles; hipótesis nunca promovidas (AG01) | RF-04 | T03, T04, T08 | 1.2 | PASS | [T03](evidence/README.md#t03), [T04](evidence/README.md#t04), [T08](evidence/README.md#t08) |
| AC05 | Presupuestos impuestos; agotamiento, malformación o fallo de citas terminan en abstención/escalamiento (AG03) | RF-05 | T02, T04, T05 | 1.3 | PASS | [T02](evidence/README.md#t02), [T04](evidence/README.md#t04), [T05](evidence/README.md#t05) |
| AC06 | Borrador con el contrato de docs/04, `uncalibrated`, `SIMULATED` y sin efecto operativo | RF-06 | T03, T09 | 1.2 | PASS | [T03](evidence/README.md#t03), [T09](evidence/README.md#t09) |
| AC07 | Interfaz de proveedores: scripted por defecto, Ollama local opcional por HTTP, externos rechazados | RF-08 | T06 | 1.4 | PASS | [T06](evidence/README.md#t06) |
| AC08 | Estados persistidos, solicitud idempotente por snapshot y ejecución única con claim/lease | RF-07 | T07 | 2.1 | PASS | [T07](evidence/README.md#t07) |
| AC09 | API con RBAC: analista solicita, lectores leen en su tenant, otro tenant 404, auditor 403 | RF-09 | T07, T09 | 2.1 | PASS | [T07](evidence/README.md#t07), [T09](evidence/README.md#t09) |
| AC10 | E2E HTTP → investigator → MCP → borrador; gate completo verde | RF-01, RF-06, RF-07 | T09, T10 | 2.2 | PASS | [T09](evidence/README.md#t09), [T10](evidence/README.md#t10), [gate](evidence/gate-all.log) |

Definition of Done de M5: AC01–AC10 en PASS con evidencia. La calidad de un modelo real no se mide en M5 (proveedor scripted, SIMULATED). El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
