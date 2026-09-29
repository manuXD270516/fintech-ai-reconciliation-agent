# Diseño de fintech-mcp-server

## Contrato y superficie

Servidor Python separado, MCP con catálogo cerrado. Stdio para desarrollo local; Streamable HTTP interno cuando lo consume el worker desplegado. Fijar SDK y revisión de protocolo mutuamente soportada en M4 y probar negociación; no asumir que la instalación de un SDK garantiza compatibilidad. MCP define inputSchema, outputSchema, resultados estructurados y anotaciones de tools. Las anotaciones son metadatos, no barreras de seguridad. [Especificación oficial de tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

Toda operación es de **lectura del negocio**. El servidor puede escribir telemetry/audit por un canal restringido sin poder mutar datos transaccionales. Credencial de servicio ligada a sujeto y tenant autorizado; `tenant_id`, scopes o permisos no se aceptan como instrucciones del modelo. Validar recurso y pertenencia en cada llamada, no sólo al listar tools.

## READ TOOLS — M4 a M10

Los nombres siguientes son el catálogo completo inicial. Los contratos son diseños, no implementaciones.

| Tool | Argumentos requeridos / opcionales | Resultado resumido | Scope |
|---|---|---|---|
| `get_transaction` | `transaction_id: UUID`; opcional `revision: int >= 1` | Observación, refs permitidas, dinero, estado, fuente y snapshot; nunca PAN/raw payload | `transactions:read` |
| `find_related_transactions` | `transaction_id: UUID`; opcionales `relation_types: enum[]`, `window_hours: 1..168`, `limit: 1..50`, `cursor` | Candidatos con criterio de relación, datos mínimos y página; no afirma que sean matches | `transactions:read` |
| `get_reconciliation_batch` | `batch_id: UUID`; opcionales `run_id: UUID`, `limit: 1..50`, `cursor` | Completitud, cutoff, rule version, totales por moneda, resultado paginado | `reconciliation:read` |
| `get_provider_status` | `provider_id: enum`; opcional `as_of: RFC3339` | Snapshot sintético con intervalo de validez, observed_at y freshness; no estado inferido de una transacción | `providers:read` |
| `search_incidents` | `query: string 1..1000`; opcionales `provider_id`, `error_code`, `as_of`, `top_k: 1..10` | Incidentes sintéticos autorizados, citas versionadas y scores con nombre del ranking | `knowledge:read` |
| `search_provider_docs` | `query: string 1..1000`, `provider_id`; opcionales `error_code`, `document_types`, `as_of`, `top_k: 1..10` | Chunks de docs, runbooks, procedimientos o códigos de error y citas | `knowledge:read` |

`get_transaction.transaction_id` identifica la observación canónica consultable, no un ID de proveedor sin scope. Rango temporal y provider_id se intersectan con permisos reales. `as_of` no convierte una fuente actual en histórica: si no existe versión aplicable devolver ausencia explícita. La paginación usa cursores opacos ligados al snapshot y sujeto; nunca SQL ni URLs proporcionadas por el LLM.

### Schema y errores

Cada input/output tiene JSON Schema versionado, campos obligatorios, enums, límites y `additionalProperties: false`. Respuesta exitosa: `data`, `provenance[]`, `snapshot_version`, `retrieved_at`, `warnings[]`, `next_cursor`. Cada provenance incluye `source_id`, `version`, `record_or_chunk_id`, `content_hash`, `locator`, `effective_at`, `synthetic`. El cliente vuelve a validar la salida antes de incorporarla al contexto.

Errores funcionales estructurados con `isError`: `NOT_FOUND`, `INVALID_ARGUMENT`, `FORBIDDEN`, `STALE_SNAPSHOT`, `RATE_LIMITED`, `DEPENDENCY_UNAVAILABLE`, `TIMEOUT`, más `retryable` y `correlation_id`. Para referencias a recursos ajenos no revelar su existencia: mapear consistentemente a `NOT_FOUND`; un scope global insuficiente puede producir `FORBIDDEN`. Errores de protocolo usan la semántica MCP correspondiente. No devolver stack traces ni consultas SQL. Un error de dependencia no devuelve una lista vacía indistinguible de “sin resultados”.

Defaults **EXPECTED**: timeout 3 s para lectura de registro y 8 s para retrieval, tamaño máximo 64 KiB por respuesta, rate limit por sujeto y máximo 2 llamadas simultáneas por run. Truncamiento explícito y paginado; no cortar una cita a mitad silenciosamente. El presupuesto total del agente prevalece sobre los límites por tool.

## WRITE TOOLS — no expuestas

Posibles herramientas futuras: `propose_resolution`, `request_adjustment`, `execute_approved_action`. No se implementan, no aparecen en `tools/list` y no reciben credenciales en M0–M10. `approve_resolution` nunca sería una herramienta del LLM: la identidad de servicio no puede representar consentimiento humano.

M6 usa comandos HTTP de case management ejecutados por usuarios humanos; persistir expedientes por el orchestrator tampoco convierte al MCP en servidor de escritura. Si se añaden tools operativas posteriormente, requieren nuevo change, scopes separados, precondiciones, aprobación de una versión exacta, límites y auditoría.

## Controles y pruebas

Roles DB SELECT en vistas autorizadas, aislamiento por tenant en aplicación y DB, consultas parametrizadas, allowlist de proveedores y ningún fetch de URL arbitraria. Auditoría registra identidad, tool, argumentos minimizados/hash, resultado, duración y referencias; nunca tokens secretos. Read-only no elimina riesgo de exfiltración: límites de filas, context minimization y authorization tests son obligatorios.

Tests previstos: discovery expone exactamente seis read tools; schemas de input/output; argumentos inválidos; recurso de otro tenant; paginación estable; timeout; datos obsoletos; prompt injection en documentos; error de dependencia; llamada a tool desconocida; integración real cliente/servidor por transporte elegido. Una prueba con identidad del agente debe demostrar que un write SQL o aprobación falla, aunque el modelo lo solicite.
