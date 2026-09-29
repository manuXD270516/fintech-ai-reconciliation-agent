# Criterios de aceptación — bootstrap-mvp-foundation

Specs escritas no equivalen a implementación aceptada. Un criterio sólo pasa a **PASS** con evidencia enlazada; `scripts/check_traceability.py` rechaza PASS/FAIL sin evidencia existente. IDs RF: [requirements](specs/repository-foundation/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Checkout limpio instala locks y completa guía sin claves externas; prerrequisitos incompletos tienen diagnóstico | RF-01 | T01, T02 | 1.1, 1.2, 1.3 | PENDING | — |
| AC02 | API/DB/vector/bus arrancan; vector query y mensaje durable funcionan; stop/start conserva marcador y mensaje pendiente | RF-02 | T03, T04 | 2.1, 2.2, 2.3 | PENDING | — |
| AC03 | Live/ready 200 sanos; cada dependencia caída produce ready 503 <= 3 s manteniendo live 200 | RF-03 | T05, T06 | 3.1, 3.2 | PENDING | — |
| AC04 | Config inválida impide arranque; API sólo loopback, dependencias privadas; sin secretos expuestos | RF-04 | T07, T08 | 1.3, 2.1, 3.3 | PENDING | — |
| AC05 | Health/log JSON correlacionados con request ID, status y duración; sin filtrar configuración | RF-05 | T09 | 3.3 | PENDING | — |
| AC06 | Gate local/CI cubre checks, sin claves IA, y falla ante contrato/spec roto | RF-06 | T10, T11 | 4.1, 4.2, 4.3 | PENDING | — |
| AC07 | README/rutas reflejan sólo M0; targets EXPECTED y fixtures sintéticos; sin endpoints financieros/agénticos | RF-07 | T12 | 5.1, 5.2 | PENDING | — |
| AC08 | Change incompleto no pasa gate documental; tasks/evidencia y archivo representan estado real | RF-08 | T11, T13 | 4.2, 5.2, 5.3 | PENDING | — |

Definition of Done de M0: AC01–AC08 satisfechos con evidencia enlazada, cero errores críticos abiertos y guía reproducida en entorno limpio. No requiere ni autoriza M1. El deadline de readiness es requisito de este change; otros presupuestos futuros siguen siendo EXPECTED.
