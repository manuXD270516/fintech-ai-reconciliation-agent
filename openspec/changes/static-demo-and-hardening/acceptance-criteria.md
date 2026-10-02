# Criterios de aceptación — static-demo-and-hardening

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/static-demo-and-hardening/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | La demo estática está publicada en Pages después del gate, es de sólo lectura y no contiene contenido prohibido | RF-01 | T01, T02 | 1.1 | PENDING | |
| AC02 | `HumanBacklog` y `ToolPermissionRefused` disparan en vivo y los drills no dejan trabajo pendiente | RF-02 | T03 | 2.1 | PENDING | |
| AC03 | El rollback de ruleset se ejercita según el runbook sin reescribir runs | RF-03 | T04 | 2.2 | PENDING | |
| AC04 | El workflow `security` pasa con gitleaks sobre toda la historia, pip-audit y npm audit; Dependabot está configurado | RF-04 | T05 | 3.1 | PENDING | |
| AC05 | La historia está documentada sin reescribirse; gate local y CI remoto en verde | RF-05 | T06 | 3.2 | PENDING | |
