# Criterios de aceptación — transaction-domain

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/transaction-domain/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Dinero exacto: roundtrip, rechazo de float/precisión/overflow/cross-currency | RF-01 | T01 | 1.1 | PASS | [T01](evidence/README.md#t01) |
| AC02 | Observaciones inmutables, acotadas y con tiempo dual; dominio sin imports de infraestructura | RF-02 | T02 | 1.2 | PASS | [T02](evidence/README.md#t02) |
| AC03 | Replay sin efecto, conflicto sin sobrescritura, revisiones nuevas y tardías correctas | RF-03 | T03, T07 | 1.3 | PASS | [T03](evidence/README.md#t03), [T07](evidence/README.md#t07) |
| AC04 | Lotes con ventana semiabierta, alcance y cutoff; inválidos rechazados | RF-04 | T04 | 1.4 | PASS | [T04](evidence/README.md#t04) |
| AC05 | Mappings versionados; valores desconocidos rechazados | RF-05 | T05 | 1.4 | PASS | [T05](evidence/README.md#t05) |
| AC06 | Dataset sintético determinístico, etiquetado y sin datos tipo tarjeta | RF-06 | T06 | 2.1 | PASS | [T06](evidence/README.md#t06) |
| AC07 | Ingesta atómica con auditoría y outbox; concurrencia y rollback sin efectos parciales | RF-07 | T07 | 3.2 | PASS | [T07](evidence/README.md#t07) |
| AC08 | Migraciones idempotentes sin drift; rol runtime sin UPDATE/DELETE/CREATE | RF-08 | T08 | 3.1 | PASS | [T08](evidence/README.md#t08) |
| AC09 | Gate completo verde y trazabilidad consistente para archivar | RF-01, RF-08 | T09 | 4.1 | PASS | [T09](evidence/README.md#t09), [gate](evidence/gate-all.log) |

Definition of Done de M1: AC01–AC09 en PASS con evidencia. El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
