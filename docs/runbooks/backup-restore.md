# Backup y restore

Ejercicio local con datos sintéticos. No es un plan de continuidad productivo: no hay réplicas, WAL archiving ni PITR.

```text
uv run python scripts/ops.py backup --out .backups/recon.dump
uv run python scripts/ops.py restore-check --dump .backups/recon.dump
```

- `backup` ejecuta `pg_dump --format=custom --schema=recon` dentro del contenedor `postgres` del proyecto. Junto al dump escribe `.backups/recon.json` con el conteo de filas por tabla y un digest del audit trail (md5 encadenado de cada fila de `audit_entries` en orden de `id`). `.backups/` está en `.gitignore`.
- `restore-check` crea la base temporal `recon_restore_check` en el mismo servidor y restaura ahí el dump con `pg_restore --exit-on-error`. Después compara conteos y digest con lo registrado al hacer el backup, mide el tiempo de restore y borra la base temporal. **La base viva no se modifica.**

## Qué mide (MEASURED, una ejecución local)

- **RTO del ejercicio:** `restore_seconds`, el tiempo de `pg_restore` sobre este volumen sintético. No predice el tiempo con datos reales.
- **RPO del ejercicio:** `rows_written_after_backup`, las filas escritas en la base viva después del backup. Con backups manuales, el RPO es el intervalo entre backups.
- **Integridad:** `counts_match_backup` y `audit_digest_match_backup`. Si cualquiera da `false`, el restore no es válido.

## Restore real (destructivo; sólo con decisión humana explícita)

No está automatizado a propósito. Exige detener `api`, `worker` e `investigator` de este proyecto, restaurar sobre una base nueva y repuntar `POSTGRES_DB`. Después, dejar que el relay publique el outbox pendiente: los consumidores deduplican por inbox, así que no se duplican efectos.
