# Criterios de aceptación — deterministic-reconciliation

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/deterministic-reconciliation/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Recepción idempotente: replay sin efectos, clave reutilizada con otro contenido rechazada, tenant del canal | RF-01 | T04, T05 | 1.2 | PASS | [T04](evidence/README.md#t04), [T05](evidence/README.md#t05) |
| AC02 | Cuarentena por fila con código; filas válidas no bloqueadas; encabezado inválido rechaza el artefacto | RF-02 | T01 | 1.1 | PASS | [T01](evidence/README.md#t01) |
| AC03 | EXACT sólo con referencia fuerte única, dinero idéntico y estado igual; diferencias enlazadas; RC05/RC06/RC12 sin match forzado | RF-04 | T02, T03 | 2.1 | PASS | [T02](evidence/README.md#t02), [T03](evidence/README.md#t03) |
| AC04 | Ranking débil explicable con empates conservados; importe y hora solos nunca hacen match | RF-05 | T02 | 2.1 | PASS | [T02](evidence/README.md#t02) |
| AC05 | WAITING_SOURCE antes de cutoff/completitud y MISSING después; duplicados y errores de proceso tipados; completitud explícita | RF-03, RF-06, RF-07 | T02, T03, T07 | 2.1 | PASS | [T02](evidence/README.md#t02), [T03](evidence/README.md#t03), [T07](evidence/README.md#t07) |
| AC06 | Runs reproducibles y versionados: snapshot hash, orden independiente, rerun y llegada tardía sin tocar el run anterior | RF-08 | T02, T04 | 2.2 | PASS | [T02](evidence/README.md#t02), [T04](evidence/README.md#t04) |
| AC07 | Outbox → JetStream → worker con inbox: entrega repetida sin doble efecto; eventos de ingestion idempotentes; poison a DLQ | RF-01, RF-09 | T04, T05 | 1.2, 3.1 | PASS | [T04](evidence/README.md#t04), [T05](evidence/README.md#t05) |
| AC08 | API `/v1` con JWT RS256 y RBAC: 401/403/404 correctos, catálogo exacto sin movimiento de dinero ni agentes | RF-10 | T06, T07 | 3.2 | PASS | [T06](evidence/README.md#t06), [T07](evidence/README.md#t07) |
| AC09 | Migración `0002` sin drift e idempotente; rol runtime sin UPDATE/DELETE sobre resultados, cuarentena, artefactos e inbox | RF-08, RF-09 | T08 | 3.3 | PASS | [T08](evidence/README.md#t08) |
| AC10 | E2E Compose: ingest HTTP + runs por bus coinciden con el oráculo v2 (44/44) | RF-01, RF-04, RF-06, RF-07, RF-09 | T07 | 4.1 | PASS | [T07](evidence/README.md#t07), [smoke](evidence/smoke.json) |
| AC11 | Ruta determinística sin clientes de modelos (cero llamadas LLM en exactos); gate completo verde | RF-11 | T09 | 4.1 | PASS | [T09](evidence/README.md#t09), [gate](evidence/gate-all.log) |

Definition of Done de M2: AC01–AC11 en PASS con evidencia. El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
