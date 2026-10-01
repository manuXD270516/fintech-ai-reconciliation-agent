# Base de datos llena o caída

**Alertas:** `MetricsSourceDown{source="database"}`; `/health/ready` en 503 con `database` en `fail`. El sistema no tiene alerta de disco propia: Docker Desktop no expone métricas de disco del volumen y no se agregó un exporter. Es una limitación conocida.

**Impacto:** sin PostgreSQL no hay ingestion, runs, investigaciones ni decisiones. Los comandos fallan con 5xx sin escribir nada parcial, porque cada comando es una transacción.

## Diagnóstico

```text
docker compose ps postgres
docker compose logs --tail 50 postgres            # "No space left on device", "could not extend file"
docker compose exec postgres df -h /var/lib/postgresql/data
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT pg_size_pretty(pg_database_size(current_database()))"'
```

## Mitigación

1. Disco lleno: liberar espacio en el host o ampliar el disco de Docker Desktop. **No** borrar filas de `audit_entries`, `transaction_observations` ni `decisions`: son append-only por diseño.
2. Hacer un backup antes de cualquier intervención: `uv run python scripts/ops.py backup` (ver [backup-restore](backup-restore.md)).
3. Contenedor caído: `docker compose up -d postgres`. El volumen `recon-m0_pgdata` conserva los datos (smoke M0 `T04`).

## Verificación

`/health/ready` vuelve a 200 y `recon_metrics_source_up{source="database"}` vale 1. Los eventos que quedaron en el outbox se publican solos (ver [broker-down](broker-down.md)).
