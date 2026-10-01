## Context

Implementa M9 de [docs/09-roadmap.md](../../../../docs/09-roadmap.md) con D09 de [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md) y la sección de observabilidad de [docs/08-risks.md](../../../../docs/08-risks.md).

## Goals / Non-Goals

**Goals:** trazas de punta a punta opcionales, métricas agregadas, alertas verificadas por fault injection, operación auditada, restore demostrado, revisión de auth/ACL y secretos.

**Non-Goals:** stack Prometheus/Grafana, paging, SLOs medidos, HA/PITR, escáneres externos.

## Decisions

- **Telemetría en `recon_store.telemetry`.**
  - Es el paquete que ya importan todos los procesos, y el outbox necesita leer el span activo en el `default` de la columna `trace_context`. Así cubre las cinco inserciones existentes sin tocarlas.
  - Sin `OTEL_EXPORTER_OTLP_ENDPOINT` se usa el tracer no-op de la API de OpenTelemetry: no se escribe contexto y no hay costo.
  - El SDK MCP ya propaga `traceparent` en `_meta` y crea spans de servidor, así que basta con configurar el SDK en el proceso MCP.
  - Exportador OTLP/HTTP: `opentelemetry-sdk` y `opentelemetry-exporter-otlp-proto-http` 1.45.0, que coinciden con la `opentelemetry-api` que ya fijaba `mcp`.
- **Perfil `observability`.** Collector 0.162.0 recibe OTLP/HTTP, borra atributos sensibles por defensa y reenvía a Jaeger 2.21.0, que guarda en memoria y publica la UI en `127.0.0.1:18186`. El demo usa la API `/api/v3` (OTLP JSON) de Jaeger v2.
- **`/metrics` sin dependencia nueva.**
  - El formato de exposición se genera a mano: contadores e histogramas HTTP en proceso y un snapshot en el momento del scrape (agregados SQL y backlog del consumidor `dlq-triage`), bajo un deadline.
  - Las series derivadas de auditoría (rechazos de decisión y llamadas MCP) usan una ventana de 1 h para que las alertas se puedan limpiar.
- **Latidos en tabla.** El worker y el investigador hacen upsert cada 10 s en `service_heartbeats`. Una fila ausente dispara la alerta: un servicio que nunca arrancó también alerta. Las demás reglas, cuya serie falta sólo si cae una fuente, tienen `absent = "ok"` y las cubre `MetricsSourceDown`.
- **Alertas como datos.** `alerts.toml` se evalúa con `recon_api.alerts`, puro y testeado. No hay `for:` ni enrutamiento: es evaluación instantánea y los umbrales son EXPECTED.
- **DLQ.**
  - Los dead letters se conservan como historia. Triar es hacer `ack` en el consumidor durable `dlq-triage`, de a un mensaje por vez para no dejar mensajes ack-pending ocultos.
  - El replay re-publica al sujeto original con `Nats-Msg-Id` determinístico, y sólo para `exhausted:`.
  - Cada acción queda auditada con el tenant del sujeto o del envelope.
- **Backup y restore.** `pg_dump -Fc --schema=recon` dentro del contenedor del proyecto y restore en `recon_restore_check` con `pg_restore --exit-on-error`. Integridad: conteos por tabla y un md5 encadenado de `audit_entries` en orden de `id`. Nunca se toca la base viva.
- **Drills.** `scripts/ops_drills.py` se ejecuta dentro del smoke. Las fallas sólo afectan servicios de este proyecto y se deshacen en `finally`. La inyección de mensajes corre en el contenedor smoke (`tests/integration/fault_injection.py`), porque NATS no se publica en el host.
- **Seguridad.**
  - La matriz ruta × rol es un test que también falla si aparece una ruta no declarada.
  - El escáner de secretos es propio (regex + Luhn + rutas prohibidas en la historia) para no descargar binarios de terceros. Se declara como heurístico.

## Risks / Trade-offs

- `/metrics` sin autenticación expone conteos agregados entre tenants. Se acepta en loopback y queda registrado en la revisión (S1).
- La alerta `OutboxStalled` necesita más de 60 s de falla, lo que alarga el smoke unos 70 s.
- El demo de trazas no es parte del gate porque descarga imágenes adicionales. Se ejecuta a mano y su salida queda como evidencia.
