# Criterios de aceptación — read-only-mcp

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/read-only-mcp/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Discovery expone exactamente seis read tools con schemas cerrados; write tools inexistentes | RF-01 | T01, T05 | 2.1 | PASS | [T01](evidence/README.md#t01), [T05](evidence/README.md#t05) |
| AC02 | SDK fijado y revisión `2025-11-25` negociada en memoria y en stdio real | RF-02 | T02, T07 | 2.1 | PASS | [T02](evidence/README.md#t02), [T07](evidence/README.md#t07) |
| AC03 | Identidad sólo del entorno; otro tenant indistinguible de inexistente; scope faltante `FORBIDDEN` | RF-03 | T04, T07 | 2.2 | PASS | [T04](evidence/README.md#t04), [T07](evidence/README.md#t07) |
| AC04 | Envelope con procedencia completa validado contra el schema por servidor y cliente | RF-04 | T03 | 2.2 | PASS | [T03](evidence/README.md#t03) |
| AC05 | Errores funcionales estructurados; dependencia caída distinta de vacío; tool desconocida es error de protocolo | RF-05 | T05 | 2.3 | PASS | [T05](evidence/README.md#t05) |
| AC06 | Timeouts, tamaño máximo con truncamiento de ítems completos, rate limit y 2 llamadas concurrentes | RF-06 | T05 | 2.3 | PASS | [T05](evidence/README.md#t05) |
| AC07 | Cursores opacos ligados a sujeto/argumentos/snapshot; alterados o ajenos rechazados; `STALE_SNAPSHOT` | RF-07 | T06 | 2.3 | PASS | [T06](evidence/README.md#t06) |
| AC08 | Búsquedas sobre retrieval híbrido con filtros duros, citas, abstención y contenido inyectado marcado | RF-08 | T03, T04, T07 | 3.1 | PASS | [T03](evidence/README.md#t03), [T04](evidence/README.md#t04), [T07](evidence/README.md#t07) |
| AC09 | Rol `recon_mcp` sólo lee evidencia e inserta auditoría; writes denegados; cada llamada auditada con hash | RF-09 | T05, T07, T08 | 1.1, 3.1 | PASS | [T05](evidence/README.md#t05), [T07](evidence/README.md#t07), [T08](evidence/README.md#t08) |
| AC10 | `transaction_uid` estable y snapshots de proveedor sin drift; estado por intervalo | RF-10 | T03, T08 | 1.1 | PASS | [T03](evidence/README.md#t03), [T08](evidence/README.md#t08) |
| AC11 | Gate completo verde y trazabilidad consistente para archivar | RF-01, RF-09 | T09 | 3.2 | PASS | [T09](evidence/README.md#t09), [gate](evidence/gate-all.log) |

Definition of Done de M4: AC01–AC11 en PASS con evidencia. El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
