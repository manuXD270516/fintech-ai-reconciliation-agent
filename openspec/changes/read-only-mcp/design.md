## Context

Implementa [docs/05-mcp.md](../../../docs/05-mcp.md) sobre la evidencia de M2 y el retrieval de M3, con las decisiones de [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md) (D12: dependencias fijadas).

## Goals / Non-Goals

**Goals:** límite de proceso real, catálogo cerrado, contratos verificables, autorización por recurso, límites y auditoría; pruebas de protocolo reales.

**Non-Goals:** Streamable HTTP, OAuth del protocolo, write tools.

## Decisions

- **SDK y revisión.** `mcp==2.2.0` (SDK oficial). Habla la era de handshake (hasta `2025-11-25`) y la era por petición `2026-07-28`. Se fija `2025-11-25` (la revisión referenciada en docs/05) usando `mode="legacy"` en los clientes; un test verifica la versión negociada en memoria y en stdio.
- **Servidor de bajo nivel.** `mcp.server.Server` con `on_list_tools` y `on_call_tool` en lugar de decoradores de alto nivel, para controlar exactamente `inputSchema`, `outputSchema` y anotaciones. La validación de entrada usa `jsonschema` (Draft 2020-12 con format checker) antes de tocar datos; la salida se valida contra su schema antes de responder (un fallo es un bug del servidor, nunca se envía).
- **Capas.** `contracts` (schemas y constantes) → `tools.ToolService` (autorización, validación, límites, cursores, truncamiento, auditoría) → `ReadBackend` (`SqlBackend` real; `MemoryBackend` de fixture para pruebas de contrato y demos offline, cuyo search es por solapamiento de términos y está rotulado como tal).
- **Identidad.** `ServiceIdentity.from_env`: `MCP_SUBJECT`, `MCP_TENANT_ID`, `MCP_SCOPES`, `MCP_KNOWLEDGE_ROLES`. El proceso que lanza el servidor (worker en M5) los fija; los schemas no tienen campos de identidad.
- **IDs.** `get_transaction` usa `transaction_uid = md5(tenant|source|source_record_id)::uuid` como columna generada `STORED` (gemelo Python en `recon_store.observations.transaction_uid`): opaco, estable entre revisiones y sin cambios en el camino de escritura de M2. MD5 aquí es un identificador, no un control de seguridad.
- **Lotes.** `batch_id` es el identificador acotado de M2 (no UUID); `run_id` sí es UUID. Desviación menor respecto de la tabla de docs/05.
- **Paginación.** Offset dentro del snapshot, codificado en un cursor `base64url(json).hmac` (HMAC-SHA256 truncado) ligado a tool, digest de argumentos (sin `cursor`/`limit`), sujeto y `snapshot_version`. Snapshot de transacciones = máximo ID de observación del tenant; de lotes = `snapshot_hash` del run.
- **Límites.** Ventana deslizante de llamadas por minuto por sujeto, `anyio.Semaphore(2)`, `anyio.fail_after` por tool con lectura en hilo (`abandon_on_cancel`), y truncamiento que elimina ítems completos y su procedencia.
- **Rol `recon_mcp`.** Creado por `db-init` (contraseña `dev-only-*`), privilegios por migración: `USAGE` en `recon`, `SELECT` en observaciones, lotes, runs, resultados, conocimiento y estado de proveedores, `INSERT` en auditoría. El INSERT de auditoría es SQL plano sin `RETURNING` porque el rol no puede leer la auditoría.
- **Estado de proveedor.** Snapshots sintéticos con intervalo de validez cargados por `knowledge-ingest`; la respuesta aclara que es estado de plataforma, no de una transacción.

## Risks / Trade-offs

- El `MemoryBackend` no reproduce el retrieval híbrido: sólo prueba contratos; el comportamiento real se prueba con `SqlBackend` en la red Compose.
- El rate limit y el semáforo son por proceso; con un servidor por investigación equivale a "por run", como pide docs/05.
- La clave de cursores es aleatoria por proceso salvo `MCP_CURSOR_KEY`; reiniciar el servidor invalida cursores (comportamiento seguro).
