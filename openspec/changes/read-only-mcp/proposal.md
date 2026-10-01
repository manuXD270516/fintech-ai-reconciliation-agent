## Why

El agente de investigación (M5) sólo debe ver evidencia a través de un límite real, con catálogo cerrado, permisos por recurso y auditoría. Si el agente consultara la base o el índice directamente, una instrucción inyectada o un argumento inventado podría cruzar tenants, leer de más o escribir. M4 crea `fintech-mcp-server`: un proceso separado, de sólo lectura, que expone exactamente seis tools con contratos versionados.

## What Changes

- **Servidor MCP** `apps/mcp-server` (`recon_mcp`) con el SDK oficial `mcp==2.2.0`, servidor de bajo nivel y revisión de protocolo fijada `2025-11-25` (handshake), probada en transporte en memoria y en stdio real con subprocess.
- **Catálogo cerrado `tools/v1`:** `get_transaction`, `find_related_transactions`, `get_reconciliation_batch`, `get_provider_status`, `search_incidents`, `search_provider_docs`, con JSON Schema de entrada y salida (`additionalProperties: false`), anotaciones de sólo lectura y ninguna write tool.
- **Identidad de servicio:** sujeto, tenant, scopes y roles de conocimiento vienen del entorno del proceso; ningún argumento puede cambiarlos. Recursos de otro tenant responden `NOT_FOUND` igual que los inexistentes; scope faltante, `FORBIDDEN`.
- **Respuestas y errores:** sobre `data`, `provenance[]`, `snapshot_version`, `retrieved_at`, `warnings[]`, `next_cursor`, `tools_version`; errores funcionales `isError` con código, `retryable` y `correlation_id`; error de dependencia distinto de "sin resultados"; tool desconocida como error de protocolo.
- **Límites:** timeouts 3 s (registros) y 8 s (retrieval), 64 KiB por respuesta con truncamiento de ítems completos, rate limit por sujeto, máximo 2 llamadas concurrentes, cursores opacos firmados ligados a sujeto, argumentos y snapshot (`STALE_SNAPSHOT`).
- **Modelo de lectura y privilegios:** migración `0004_mcp_read_model` con `transaction_uid` generado (ID estable por observación canónica), snapshots sintéticos de estado de proveedores y rol `recon_mcp` con `SELECT` sobre tablas de evidencia e `INSERT` sólo en auditoría.

## Capabilities

### New Capabilities

- `read-only-mcp`: acceso de sólo lectura, autorizado, acotado y auditado a evidencia transaccional, de conciliación, de estado de proveedores y de conocimiento mediante un catálogo MCP cerrado.

### Modified Capabilities

Ninguna en specs vigentes. `recon_knowledge` agrega un filtro opcional por tipo de documento y la carga de snapshots de estado de proveedor en el job `knowledge-ingest`; el contrato de M3 no cambia.

## Impact

Nuevo paquete `apps/mcp-server`, dependencias `mcp==2.2.0` y `jsonschema==4.26.0` (y `types-jsonschema` en dev), migración `0004`, rol `recon_mcp` en `db-init` y variables `MCP_DB_USER`/`MCP_DB_PASSWORD` (`dev-only-*`), dataset `provider-status-v1`.

Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md); diseño de referencia: [docs/05-mcp.md](../../../docs/05-mcp.md).

## Non-goals

Streamable HTTP (el worker lanzará el servidor por stdio en M5), write tools de cualquier tipo, autenticación OAuth del protocolo, uso del servidor por un modelo (M5) y UI.
