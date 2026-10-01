## Why

M1 dejó observaciones exactas e idempotentes, pero el sistema todavía no recibe fuentes ni compara nada. M2 entrega el corazón determinístico del producto: recibir artefactos sintéticos, normalizarlos con cuarentena explícita y conciliarlos 1:1 con reglas versionadas, reproducibles y auditables, sin ninguna llamada a modelos. Todo lo posterior (RAG, MCP, agentes, aprobación) consume estos resultados; si aquí hubiera falsos matches o faltantes prematuros, la IA sólo los maquillaría.

## What Changes

- **Ingestion (anti-corruption layer):** parser CSV versionado (`csv-parser/v1`) con validación fila a fila; filas inválidas van a cuarentena con código (`missing_field`, `invalid_field`, `invalid_precision`, `unknown_mapping`, `scope_violation`) sin bloquear las válidas. Recepción por HTTP (`POST /v1/artifacts`) y por eventos JetStream (`recon.ingest.<tenant>.<source>.<provider>`), ambas idempotentes por clave.
- **Batches y completitud:** creación de lotes por API y marca explícita de fuente completa (`POST /v1/batches/{id}/sources/{source}/complete`).
- **Motor `rules/v1`:** agrupación por referencia fuerte acotada; EXACT sólo con candidato único, dinero idéntico (tolerancia cero) y estado compatible; discrepancias multilabel enlazadas; ranking débil explicable con empates conservados; `WAITING_SOURCE` vs `MISSING_*` según cutoff y completitud; `DUPLICATE_CANDIDATE` y `PROCESSING_ERROR`.
- **Runs versionados:** cada run guarda snapshot hash, ruleset y resultados ordenados; un rerun crea versión nueva sin tocar las anteriores.
- **Outbox/inbox:** worker que publica el outbox en JetStream (at-least-once, `Nats-Msg-Id`), ejecuta runs con inbox `(consumer, event_id)` y envía mensajes envenenados o agotados a `RECON_DLQ`.
- **API autenticada:** JWT RS256 con JWKS local de desarrollo (verificador compatible con OIDC), roles `analyst`, `supervisor`, `auditor`, `integration`; tenant tomado del token, nunca del cuerpo.
- **Dataset `transactions-v2`:** corrige las etiquetas de v1 para pares enlazados con diferencias (no son EXACT, invariante 4); v1 queda congelado.

## Capabilities

### New Capabilities

- `deterministic-reconciliation`: recepción idempotente de fuentes sintéticas, normalización con cuarentena, lotes con completitud, conciliación determinística 1:1 versionada y publicación confiable de eventos.

### Modified Capabilities

Ninguna en la spec vigente `transaction-domain`: el modelo y sus invariantes no cambian. El dataset v1 sigue regenerándose idéntico; v2 se agrega al lado.

## Impact

Paquetes `recon_domain` (`ingestion`, `reconciliation`, `oracle`), `recon_store` (`artifacts`, `reconciliation`, `outbox`, migración `0002`), nueva app `apps/worker`, rutas `/v1/*` en la API, servicio Compose `worker`, montaje de sólo lectura del JWKS público, `scripts/dev_auth.py` y dependencias `pyjwt[crypto]`/`cryptography` fijadas.

Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md) (D06, D07, D12).

## Non-goals

Relaciones 1:N/N:1, capturas parciales, fees, netting y FX (se reportan como discrepancias, nunca se fuerzan). RAG, MCP, agentes, aprobación humana y UI (M3–M8). Ingestion desde proveedores reales o archivos en object storage. Ninguna operación mueve dinero.
