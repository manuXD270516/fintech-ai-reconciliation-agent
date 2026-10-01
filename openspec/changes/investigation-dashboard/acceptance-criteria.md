# Criterios de aceptación — investigation-dashboard

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/investigation-dashboard/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Cliente generado desde OpenAPI con detección de drift del documento y de los tipos | RF-01 | T01 | 1.1 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC02 | Navegación sobre rutas de lectura autorizadas (lotes, runs, resultados, casos) | RF-02 | T02, T07 | 1.1 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC03 | Borrador con hechos/inferencias/hipótesis separados, citas, revisión, `uncalibrated` y SIMULATED | RF-03 | T03, T07 | 2.1 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC04 | Caso con vigencia visible, propuesta y decisión con efecto exacto, versión e idempotencia; obsoleto deshabilitado; sin aprobación masiva | RF-04 | T04, T07 | 2.2 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC05 | Errores comprensibles por código sin detalles internos | RF-05 | T05, T07 | 2.2 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC06 | Flujo clave operable por teclado y sin violaciones axe serias/críticas | RF-06 | T06, T07 | 2.3 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC07 | E2E analista → supervisor → auditor contra el stack real | RF-07 | T07 | 3.1 | PASS | [evidencia](evidence/README.md#por-criterio) |
| AC08 | Paso `web` en gate y CI; gate completo verde | RF-01 | T08 | 3.1 | PASS | [evidencia](evidence/README.md#por-criterio) |

Definition of Done de M8: AC01–AC08 en PASS con evidencia. El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
