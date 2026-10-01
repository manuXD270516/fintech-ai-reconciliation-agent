# Criterios de aceptación — observability-security

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/observability-security/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Una investigación produce una traza única con api, worker, investigador y MCP, sin atributos prohibidos; apagado por defecto | RF-01 | T01 | 1.1 | PENDING | |
| AC02 | `/metrics` agregado y de baja cardinalidad, con fuentes caídas reportadas sin fallar | RF-02 | T02 | 1.2 | PENDING | |
| AC03 | Cada regla de alerta enlaza un runbook y se verifica disparando y limpiando | RF-03 | T03, T04, T05 | 2.1 | PENDING | |
| AC04 | Recuperación exacta tras la caída del broker; triage de DLQ auditado; replay sin duplicados y sin re-publicar veneno | RF-04 | T04, T05 | 2.2 | PENDING | |
| AC05 | Backup y restore-check con conteos y digest de auditoría coincidentes, tiempos medidos y sin tocar la base viva | RF-05 | T06 | 2.3 | PENDING | |
| AC06 | Runbooks con comandos reales; revocación auditada ejercitada | RF-06 | T07 | 2.4 | PENDING | |
| AC07 | Escaneo de toda la historia sin hallazgos en el gate; matriz ruta × rol aplicada; revisión con hallazgos | RF-07 | T08, T09 | 3.1 | PENDING | |
| AC08 | Gate completo verde con los drills de M9 en el smoke | RF-03, RF-04, RF-05 | T04, T05, T06 | 3.2 | PENDING | |

Definition of Done de M9: AC01–AC08 en PASS con evidencia. El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
