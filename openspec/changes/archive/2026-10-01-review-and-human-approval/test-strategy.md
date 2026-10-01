# Estrategia de pruebas — M6

Unitarias para el revisor (con cliente MCP real en memoria y proveedor scripted) y la política pura de aprobación; integración contra PostgreSQL real para casos, decisiones, concurrencia y auditoría; E2E HTTP en el smoke.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Revisor | Revisión `SUPPORTED` en el flujo fiel, revisor que rechaza → `ABSTAINED`, entrada aislada (sólo caso, afirmaciones, citas), chequeos determinísticos (diferencia, ambos lados, hipótesis, contradicción) y combinación conservadora (`tests/unit/test_reviewer.py`, `test_agents.py`) |
| T02 | Reflexión | Una reflexión con presupuesto 5 (dos revisiones, `DRAFTED`); con el presupuesto por defecto no cabe y se escala (`test_reviewer.py`) |
| T03 | Política | Decisión válida, diez rechazos (rol, autoaprobación por proponente y por solicitante de la investigación, motivo, versión del caso y de la recomendación, estado, no pendiente, obsoleta, expirada), propiedad Hypothesis HU01, reglas de propuesta y cierre (`tests/unit/test_approval_policy.py`) |
| T04 | Flujo completo | PostgreSQL real: investigación real → caso idempotente → recomendación que adopta el borrador `SUPPORTED` → aprobación → replay idempotente → clave reutilizada en conflicto → cierre → traza con apertura, recomendación, decisión, cierre, investigación (pasos y citas) y un único `ApprovalRecorded` sin efecto operativo (`tests/integration/test_cases_flow.py`) |
| T05 | HU01 y HU02 | Autoaprobación denegada, caso intacto y `decision.denied` auditado; cuatro supervisores concurrentes → una decisión y el resto conflictos (mismo archivo) |
| T06 | Versión, expiración, obsolescencia | Versión vieja → `version_conflict`; recomendación de hace 4 días → `recommendation_expired`; run más nuevo → `recommendation_obsolete` y estado `OBSOLETE`; borrador de otro resultado no adoptable (mismo archivo) |
| T07 | Privilegios | Rol runtime sin UPDATE/DELETE de decisiones, sin reescribir recomendaciones ni autoría de casos; drift `0006` (mismo archivo, `test_store.py`) |
| T08 | E2E HTTP | Smoke `M6-T08`: caso 201, recomendación 201 adoptando el borrador del paso M5, autoaprobación 403, analista decide 403, versión vieja 409, aprobación 201 con `operational_effect` "none…", replay 200, traza del auditor con `decision.denied`/`decision.record`, analista no lee la traza (403) |
| T09 | Gate | `scripts/gate.py all` y catálogo exacto de rutas |

## Ejecución y evidencias

`uv run python scripts/gate.py all`. Evidencia en [evidence/](evidence/README.md). Salidas del modelo SIMULATED (scripted).

## Stop condition

M6 no agrega UI, ejecución financiera ni aprobaciones masivas.
