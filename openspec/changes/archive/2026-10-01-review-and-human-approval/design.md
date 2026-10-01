## Context

Implementa la revisión y el human-in-the-loop de [docs/04-agents.md](../../../../docs/04-agents.md) y las transacciones críticas de [docs/02-architecture.md](../../../../docs/02-architecture.md#interfaces-y-consistencia), con D07 de [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md).

## Goals / Non-Goals

**Goals:** ninguna autoaprobación, una sola transición ante concurrencia, decisiones obsoletas imposibles, auditoría reconstruible, revisión aislada y conservadora.

**Non-Goals:** UI, calibración, ejecución financiera.

## Decisions

- **Revisión antes de la persona.** El revisor corre dentro de la misma investigación (estado `DRAFTED` sólo si la revisión es `SUPPORTED`; `NEEDS_MORE_EVIDENCE` final → `ESCALATED`; `REJECTED` → `ABSTAINED`). Los chequeos determinísticos se ejecutan primero; si ya rechazan, no se gasta la llamada del modelo.
- **Presupuesto y reflexión.** Con el presupuesto EXPECTED (4 llamadas generativas) y la planificación con modelo de M5, la investigación usa plan + borrador + revisión = 3, de modo que la pareja de reflexión no cabe y se escala. Es un hallazgo explícito: docs/04 suponía un plan sólo por plantilla. La reflexión se prueba con un presupuesto de 5 llamadas.
- **Política pura.** `recon_domain.approval.check_decision` es una tabla ordenada (identidad antes que estado) probada sin base de datos, incluida una propiedad Hypothesis de "nadie aprueba su propia propuesta".
- **Serialización.** `SELECT … FOR UPDATE` sobre el caso dentro de la transacción del comando; idempotencia por `uq_decision_idempotency (tenant, key)` comprobada bajo el lock; `uq_decision_per_recommendation` como segunda barrera.
- **Rechazos auditados.** La transacción del comando no escribe nada si la política rechaza; una segunda transacción registra `decision.denied` y, si la causa es un run más nuevo, marca la recomendación `OBSOLETE`.
- **Obsolescencia.** El caso apunta a un run; si existe un run completado con número mayor para el mismo lote, la recomendación no es aprobable (RC10). La expiración (72 h) se fija al proponer.
- **Estados.** Caso: `OPEN → HUMAN_REVIEW → APPROVED | REJECTED | NEEDS_INFORMATION`, `CLOSED` por comando humano desde aprobado/rechazado; tras rechazo o pedido de información se puede proponer de nuevo. La investigación conserva su propio ciclo (M5), por eso el caso no replica `INVESTIGATING`/`REVIEW_PENDING` (simplificación documentada).
- **Auditoría reconstruible.** `audit_trail` junta caso, run (ruleset y snapshot hash), recomendaciones, decisiones, investigaciones adoptadas (pasos MCP, citas, revisión) y entradas de auditoría por ID de recurso; la propia lectura se audita.

## Risks / Trade-offs

- La revisión scripted no mide independencia real entre modelos; sólo prueba el contrato y la combinación conservadora.
- La segregación se basa en `sub` del token; un IdP real debería garantizar identidades únicas y revocación.
- Las acciones son un conjunto cerrado no operativo; agregar acciones con efectos externos requeriría otro change y threat model.
