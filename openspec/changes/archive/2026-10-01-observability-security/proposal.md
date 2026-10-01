## Why

M9 del roadmap exige demostrar que el sistema se puede operar y que sus controles resisten fallas: telemetría que siga una operación de punta a punta, alertas verificadas, runbooks ejecutables, replay y restore demostrados, revisión de auth/ACL y secretos escaneados. Hasta M8 sólo existían logs JSON con request ID y readiness.

## What Changes

- **Trazas (D09):** SDK OpenTelemetry con propagación W3C `traceparent` HTTP → outbox (columna `trace_context`) → NATS → worker / investigador → MCP (`_meta`, SDK oficial). Apagado por defecto; perfil Compose `observability` con OpenTelemetry Collector y Jaeger fijados por digest, sólo en loopback.
- **Métricas:** `GET /metrics` en formato Prometheus. Incluye contadores e histogramas HTTP por plantilla de ruta, y agregados de outbox, latidos de servicio, runs, resultados, investigaciones (presupuesto y tokens), revisiones, cola humana, rechazos de decisión, llamadas MCP y dead letters sin triar. No incluye tenant, sujeto ni IDs.
- **Latidos:** el worker y el investigador escriben `service_heartbeats` (migración `0007_observability`).
- **Alertas:** reglas EXPECTED de docs/08 en `infra/observability/alerts.toml`, evaluadas por `scripts/ops.py alerts`.
- **Operación:**
  - Triage auditado de dead letters (`python -m recon_worker.dlq`): replay sólo de entregas agotadas, nunca de mensajes veneno.
  - Revocación auditada de documentos (`python -m recon_knowledge revoke`).
  - `scripts/ops.py backup|restore-check`.
  - Runbooks en `docs/runbooks/`.
- **Drills en el smoke:**
  - `M9-T04`: métricas y alertas en el stack sano.
  - `M9-T05`: caída de broker y worker, dead letters y replay idempotente.
  - `M9-T06`: backup y restore con conteos y digest del audit trail.
- **Seguridad:**
  - Matriz ruta × rol verificada por test.
  - Revisión documentada con hallazgos (`docs/security-review.md`).
  - Paso de gate `secrets` que escanea toda la historia git; CI hace checkout completo.

## Capabilities

### New Capabilities

- `observability-security`: telemetría opcional, métricas, alertas verificadas, operación auditada (DLQ, revocación, backup) y revisión de seguridad.

### Modified Capabilities

Ninguna en specs vigentes. La API agrega la ruta pública `/metrics`, y el outbox una columna nullable sin cambio de comportamiento.

## Impact

`packages/store` (telemetría, `ops`, migración 0007), API (middleware, `/metrics`), worker, investigador, servidor MCP, `compose.yaml` (perfil `observability`), `infra/observability/`, `scripts/` (ops, drills, demo de trazas, secret scan), gate y CI. Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md) (D09).

## Non-goals

Prometheus/Grafana desplegados, alertmanager o paging, SLOs medidos, HA, PITR, TLS interno, pentest o escáneres externos de vulnerabilidades.
