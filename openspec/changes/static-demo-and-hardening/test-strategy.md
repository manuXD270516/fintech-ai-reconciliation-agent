# Estrategia de pruebas — static-demo-and-hardening

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Modo demo | Vitest `src/test/demo.test.ts`: GET servidos y filtrados como en la API, 404 para lo no capturado, mutaciones 403 `demo_read_only`, reaperturas idempotentes, auditoría restringida y sesiones sin firma |
| T02 | Sitio publicado | Workflow `pages` (Vitest, build y grep de contenido prohibido) después de `ci` en verde; la URL pública responde y la demo navega lotes → investigación → caso |
| T03 | Alertas en vivo | Smoke `M11-T02`: `HumanBacklog` dispara y vuelve a la base; `ToolPermissionRefused` dispara con un `FORBIDDEN` real auditado |
| T04 | Rulesets | Unit `tests/unit/test_rulesets.py` (v1 = etiquetas; v2 sólo convierte PROBABLE en UNMATCHED; versión desconocida rechazada) y smoke `M11-T03` (rollback según el runbook) |
| T05 | Supply chain | Workflow `security` en verde: gitleaks sobre toda la historia, pip-audit y npm audit; ejecución local previa de gitleaks, pip-audit y npm audit |
| T06 | Gate | `scripts/gate.py all` en local y `ci` remoto en verde |

## Ejecución y evidencias

Gate local más los runs remotos `ci`, `security` y `pages`. Evidencia en [evidence/](evidence/README.md).
