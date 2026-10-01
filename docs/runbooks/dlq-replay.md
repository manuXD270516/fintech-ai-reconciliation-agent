# Dead letters y replay

**Alerta:** `DeadLetters` (`recon_dead_letters_unhandled > 0`). El valor sale del consumidor durable `dlq-triage` del stream `RECON_DLQ`: son los dead letters que todavía nadie trió.

**Origen:** un mensaje llega a `recon.dlq.<consumer>` cuando es veneno (JSON inválido, sujeto o `event_id` inválidos, tamaño excesivo) o cuando agotó 5 entregas (`exhausted: <error>`). El mensaje conserva el sujeto original, el motivo y los datos.

## Diagnóstico

```text
docker compose exec worker python -m recon_worker.dlq list
```

Lista cada dead letter sin triar con su secuencia, sujeto original, motivo y si es re-publicable. Sólo se re-publican los `exhausted:` de `recon.events.*` y `recon.ingest.*`: un mensaje veneno nunca va a funcionar y sólo se puede descartar.

## Decisión

| Motivo | Acción |
|---|---|
| `poison: ...` (el mensaje nunca va a funcionar) | `discard` con motivo; corregir el productor |
| `exhausted: ...` por una dependencia ya recuperada | `replay` |
| Dudoso | No triar; escalar. La alerta sigue activa a propósito |

```text
docker compose exec worker python -m recon_worker.dlq triage --action discard --operator ops-ana --reason "evento malformado del proveedor X; corregido en origen" --limit 1
docker compose exec worker python -m recon_worker.dlq triage --action replay  --operator ops-ana --reason "NATS recuperado" --limit 5
```

Los mensajes se trían en orden. `replay` se detiene ante el primero que no se puede re-publicar.

## Garantías

- El replay re-publica al sujeto original con `Nats-Msg-Id = dlq-replay-<seq>`. Los consumidores son idempotentes (inbox y clave de idempotencia del artefacto), así que repetir un replay no duplica efectos (smoke `M9-T05`).
- Cada acción inserta en `audit_entries` un registro con `dlq.replay` o `dlq.discard`, el operador, el motivo y la secuencia.
- Los dead letters no se borran: quedan 7 días en `RECON_DLQ` como historia y triar sólo los confirma (`ack`) en `dlq-triage`.
