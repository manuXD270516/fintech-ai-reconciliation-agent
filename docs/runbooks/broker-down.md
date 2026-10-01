# Broker o relay caído

**Alertas:** `OutboxStalled` (evento del outbox pendiente > 60 s), `WorkerHeartbeatMissing` (worker sin latido > 60 s), `MetricsSourceDown{source="messaging"}`.

**Impacto:** la API sigue aceptando comandos y los guarda en el outbox dentro de la misma transacción; los runs e investigaciones solicitados no avanzan. `/health/ready` responde 503 con `messaging` en `fail`. No se pierde nada: el outbox es la fuente de verdad.

## Diagnóstico

```text
uv run python scripts/ops.py alerts
curl -s http://127.0.0.1:18180/health/ready
curl -s http://127.0.0.1:18180/metrics | findstr "outbox heartbeat source_up"   # grep en bash
docker compose ps nats worker
docker compose logs --tail 50 nats worker
```

## Mitigación

1. Si `nats` está detenido o sin healthcheck: `docker compose start nats` (o `docker compose up -d nats`).
2. Si el worker está caído: `docker compose up -d worker`. Tiene `restart: unless-stopped`.
3. No publicar a mano en JetStream ni editar filas del outbox: el relay reintenta solo y `Nats-Msg-Id` deduplica.

## Verificación

- `recon_outbox_pending` vuelve a 0 y `OutboxStalled` deja de disparar.
- Los consumidores deduplican por inbox, así que los eventos re-publicados no duplican efectos. El smoke `M9-T05` lo verifica: un run pedido con el broker caído se completa una sola vez después de la recuperación.
