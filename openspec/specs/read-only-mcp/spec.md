# read-only-mcp Specification

## Purpose
Exponer evidencia transaccional, de conciliación, de estado de proveedores y de conocimiento mediante un catálogo MCP cerrado de seis tools de sólo lectura, con identidad de servicio, autorización por recurso, límites, paginación firmada y auditoría.

## Requirements

### Requirement: RF-01 Closed read-only tool catalog

El servidor SHALL exponer exactamente seis tools (`get_transaction`, `find_related_transactions`, `get_reconciliation_batch`, `get_provider_status`, `search_incidents`, `search_provider_docs`), cada una con JSON Schema de entrada y salida versionados (`tools/v1`) donde todo objeto declara `additionalProperties: false`, y anotaciones de sólo lectura. Ninguna tool de escritura, aprobación o resolución MUST aparecer en `tools/list` ni ser invocable.

#### Scenario: Discovery
- **WHEN** un cliente lista las tools
- **THEN** recibe exactamente las seis, todas `readOnlyHint` y sin argumentos de identidad

#### Scenario: Write tool requested
- **WHEN** un cliente invoca `approve_resolution`
- **THEN** recibe un error de protocolo de tool desconocida

### Requirement: RF-02 Pinned protocol and verified transports

El servidor SHALL usar una versión fijada del SDK oficial y MUST negociar la revisión de protocolo `2025-11-25` en el handshake. La negociación y las llamadas MUST verificarse tanto en transporte en memoria como en stdio real con el servidor como proceso separado.

#### Scenario: Stdio subprocess
- **WHEN** un cliente lanza `python -m recon_mcp` por stdio
- **THEN** la sesión negocia `2025-11-25`, lista seis tools y obtiene resultados válidos

### Requirement: RF-03 Service identity and resource authorization

Sujeto, tenant, scopes y roles de conocimiento SHALL provenir de la credencial de servicio del proceso y MUST NOT aceptarse como argumentos. Cada llamada MUST verificar el scope requerido y la pertenencia del recurso al tenant; un recurso de otro tenant MUST responder igual que uno inexistente.

#### Scenario: Cross-tenant identifier
- **WHEN** se pide una transacción que existe en otro tenant
- **THEN** la respuesta es `NOT_FOUND` con el mismo mensaje que para un ID inexistente

#### Scenario: Missing scope
- **WHEN** la identidad no tiene `knowledge:read` y se llama `search_incidents`
- **THEN** la respuesta es `FORBIDDEN`

### Requirement: RF-04 Structured envelope with provenance

Toda respuesta exitosa SHALL incluir `data`, `provenance[]` (fuente, versión, ID de registro o chunk, hash, localizador, fecha efectiva y `synthetic`), `snapshot_version`, `retrieved_at`, `warnings[]`, `next_cursor` y `tools_version`. El servidor MUST validar su salida contra el schema antes de responder y el cliente MUST poder revalidarla.

#### Scenario: Non-current revision
- **WHEN** se pide una revisión anterior de una observación
- **THEN** la respuesta la devuelve con una advertencia que indica la revisión vigente

### Requirement: RF-05 Structured functional errors

Los errores funcionales SHALL devolverse con `isError` y un objeto con `code` (`NOT_FOUND`, `INVALID_ARGUMENT`, `FORBIDDEN`, `STALE_SNAPSHOT`, `RATE_LIMITED`, `DEPENDENCY_UNAVAILABLE`, `TIMEOUT`), `retryable` y `correlation_id`, sin trazas ni SQL. Un fallo de dependencia MUST NOT presentarse como resultado vacío.

#### Scenario: Backend outage
- **WHEN** el almacenamiento falla durante una llamada
- **THEN** la respuesta es `DEPENDENCY_UNAVAILABLE` con `retryable: true`

### Requirement: RF-06 Bounded execution

Cada tool SHALL tener un timeout (3 s registros, 8 s retrieval), las respuestas MUST quedar bajo 64 KiB eliminando ítems completos con advertencia y sin cortar citas, el servidor MUST limitar la tasa por sujeto y MUST NOT ejecutar más de dos llamadas simultáneas.

#### Scenario: Slow backend
- **WHEN** una lectura excede su timeout
- **THEN** la respuesta es `TIMEOUT` y la llamada no bloquea al servidor

#### Scenario: Concurrency
- **WHEN** llegan cinco llamadas a la vez
- **THEN** como máximo dos se ejecutan simultáneamente

### Requirement: RF-07 Opaque bound pagination

Las tools paginadas SHALL devolver cursores opacos firmados ligados a la tool, los argumentos, el sujeto y el snapshot. Un cursor alterado o de otra petición MUST rechazarse con `INVALID_ARGUMENT` y uno emitido sobre datos que cambiaron MUST rechazarse con `STALE_SNAPSHOT`.

#### Scenario: Data changed
- **WHEN** se reutiliza un cursor después de que cambió el snapshot
- **THEN** la respuesta es `STALE_SNAPSHOT`

### Requirement: RF-08 Knowledge tools over hybrid retrieval

`search_incidents` y `search_provider_docs` SHALL usar la recuperación híbrida de M3 con los filtros duros del contexto de servicio, restringidas a incidentes o a documentos de proveedor/códigos/runbooks/procedimientos respectivamente, con citas `[document@version#chunk]`, abstención explícita y contenido con instrucciones marcado `untrusted_instructions` con advertencia.

#### Scenario: Injected document
- **WHEN** un resultado contiene instrucciones dirigidas al modelo
- **THEN** se devuelve como dato marcado y con advertencia, sin ejecutar nada

### Requirement: RF-09 Least-privilege database identity and audit

El servidor SHALL conectarse con un rol propio que sólo pueda leer las tablas de evidencia e insertar auditoría. Cada llamada MUST auditarse con sujeto, tool, hash de argumentos, resultado, duración y referencias devueltas, sin argumentos en claro ni secretos. Cualquier write sobre datos de negocio con ese rol MUST fallar en la base de datos.

#### Scenario: Write with the MCP identity
- **WHEN** el rol del servidor intenta actualizar resultados o borrar auditoría
- **THEN** PostgreSQL lo rechaza por privilegios insuficientes

### Requirement: RF-10 Stable read model

La migración `0004` SHALL agregar un `transaction_uid` generado y estable para cada clave de observación (igual en todas sus revisiones) y una tabla de snapshots de estado de proveedor con intervalo de validez, sin drift respecto de las definiciones Core.

#### Scenario: Provider status at a time
- **WHEN** se consulta el estado de prov-alfa en una fecha dentro de un incidente
- **THEN** se devuelve el snapshot válido con `observed_at` y `freshness_seconds`, aclarando que no es el estado de una transacción
