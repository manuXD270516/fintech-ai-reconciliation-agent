## Why

Un borrador de investigación no es una decisión. M6 cierra el MVP técnico: un revisor independiente evalúa cada borrador antes de que una persona lo vea, y las decisiones operativas sólo existen como comandos humanos autorizados, versionados, idempotentes y auditados. La aprobación registra una decisión; nunca ejecuta movimientos de dinero.

## What Changes

- **Reviewer:** chequeos determinísticos primero (problemas de verificación, elementos requeridos del caso, hipótesis sin evidencia necesaria, contradicciones) y una revisión del modelo aislada (sólo snapshot, hechos, afirmaciones y citas); el resultado es el más conservador entre `SUPPORTED`, `NEEDS_MORE_EVIDENCE` y `REJECTED`. Una reflexión como máximo tras una objeción accionable y sólo si cabe en el presupuesto; si no, abstención o escalamiento.
- **Política de aprobación pura** (`recon_domain.approval`): segregación de funciones (ni el proponente ni quien pidió la investigación pueden decidir), rol supervisor, motivo obligatorio, versión vigente, estado del caso, recomendación pendiente, expiración (72 h) y obsolescencia cuando existe un run más nuevo del lote.
- **Case management** (migración `0006_cases`): casos por resultado, recomendaciones propuestas por analistas (adoptar un borrador exige revisión `SUPPORTED`), decisiones de supervisores con clave de idempotencia y cierre con motivo; todo bajo lock de fila con auditoría y outbox (`ApprovalRecorded`, `CaseClosed`) en la misma transacción; intentos rechazados auditados.
- **API:** `POST /v1/runs/{run_id}/results/{ordinal}/cases`, `GET /v1/cases/{id}`, `POST /v1/cases/{id}/recommendations`, `POST /v1/cases/{id}/decisions`, `POST /v1/cases/{id}/close`, `GET /v1/cases/{id}/audit` (reconstrucción de insumos, reglas, consultas, fuentes y decisión).

## Capabilities

### New Capabilities

- `review-and-human-approval`: revisión independiente de borradores y decisiones humanas versionadas, idempotentes, con segregación de funciones y auditoría reconstruible.

### Modified Capabilities

Ninguna en specs vigentes. La investigación (M5) agrega la revisión y la reflexión acotada a su máquina de estados; su contrato de borrador incorpora `review_result`.

## Impact

Módulos `recon_agents.reviewer`, `recon_domain.approval`, `recon_store.cases`, migración `0006`, seis rutas `/v1` y el paso smoke `M6-T08`.

Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md) (D07: RBAC y segregación); diseño: [docs/04-agents.md](../../../docs/04-agents.md#human-in-the-loop).

## Non-goals

Calibración de confianza, UI (M8), aprobaciones masivas, ejecución financiera de cualquier tipo, revocación de sesiones en el IdP (los tokens de desarrollo expiran) y SLA de cola humana.
