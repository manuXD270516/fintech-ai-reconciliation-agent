# Criterios de aceptación — review-and-human-approval

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/review-and-human-approval/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Revisión determinística + modelo aislado, resultado conservador y nunca equivalente a aprobación humana | RF-01 | T01 | 1.1 | PASS | [T01](evidence/README.md#t01) |
| AC02 | Como máximo una reflexión y sólo dentro del presupuesto; si no, escalamiento con motivo | RF-02 | T02 | 1.1 | PASS | [T02](evidence/README.md#t02) |
| AC03 | Recomendaciones sólo de analistas; adoptar un borrador exige el mismo caso y revisión `SUPPORTED` | RF-03 | T04, T06 | 2.2 | PASS | [T04](evidence/README.md#t04), [T06](evidence/README.md#t06) |
| AC04 | Sin autoaprobación (proponente o solicitante), rechazos auditados (HU01) | RF-04 | T03, T05, T08 | 2.1 | PASS | [T03](evidence/README.md#t03), [T05](evidence/README.md#t05), [T08](evidence/README.md#t08) |
| AC05 | Versión vigente, expiración, obsolescencia por run nuevo (RC10), idempotencia y una sola transición concurrente (HU02) | RF-05 | T03, T05, T06, T08 | 2.1, 2.2 | PASS | [T03](evidence/README.md#t03), [T05](evidence/README.md#t05), [T06](evidence/README.md#t06), [T08](evidence/README.md#t08) |
| AC06 | Decisión, estado, auditoría y evento en una transacción; sin movimiento de dinero; cierre humano con motivo | RF-06 | T04, T08 | 2.2 | PASS | [T04](evidence/README.md#t04), [T08](evidence/README.md#t08) |
| AC07 | Traza reconstruible para auditor/supervisor (insumos, reglas, consultas, fuentes, decisión), lectura auditada, analista 403 | RF-07 | T04, T08 | 2.3 | PASS | [T04](evidence/README.md#t04), [T08](evidence/README.md#t08) |
| AC08 | Rol runtime sin modificar ni borrar decisiones, recomendaciones o autoría; migración sin drift | RF-08 | T07 | 2.2 | PASS | [T07](evidence/README.md#t07) |
| AC09 | E2E HTTP del flujo analista → supervisor y gate completo verde | RF-03, RF-04, RF-05, RF-06 | T08, T09 | 3.1 | PASS | [T08](evidence/README.md#t08), [T09](evidence/README.md#t09), [gate](evidence/gate-all.log) |

Definition of Done de M6 (cierre del MVP técnico M0–M6): AC01–AC09 en PASS con evidencia. El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
