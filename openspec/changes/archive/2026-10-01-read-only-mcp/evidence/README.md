# Evidencia — read-only-mcp (M4)

Ejecutada el 2026-10-01 en Windows 11 (Docker 29.8.1, Compose 5.5.1, linux/amd64), rama `m4-read-only-mcp` con cambios sin commitear (el smoke registra `dirty: true`). Evidencia **MEASURED** local con datos sintéticos; no es benchmark. CI remoto no ejecutado (bloqueo de facturación de GitHub, AC06 de M0).

Archivos:

- [gate-all.log](gate-all.log): `uv run python scripts/gate.py all`, todos PASS; 196 tests unitarios; smoke 15/15.
- [unit-tests.log](unit-tests.log): `pytest -v tests/unit/test_mcp_server.py` (22 passed).
- [smoke.json](smoke.json): 62 tests de integración en la red Compose, 13 de ellos en `test_mcp_sql.py`.

## T01

`test_discovery_exposes_exactly_six_read_tools`: seis tools en el orden del catálogo, `read_only_hint=True`, `destructive_hint=False`, `outputSchema` presente, todos los objetos de entrada y salida con `additionalProperties: false`, sin `tenant_id`/`scopes`/`subject` como argumentos y sin nombres de escritura. Ver [unit-tests.log](unit-tests.log).

## T02

`test_protocol_revision_is_negotiated` (`2025-11-25`, `server_info.name == fintech-mcp-server`) y `test_real_stdio_transport_with_subprocess` (proceso `python -m recon_mcp --backend fixture` por stdio: misma revisión, seis tools, resultado válido). Ver [unit-tests.log](unit-tests.log).

## T03

Revisión vigente 2 y revisión 1 con advertencia "revision 1 is not current (2)", procedencia con localizador `internal_ledger/led-000001@2` y `synthetic: true`, sin `raw_hash` en `data`; relacionadas con criterios explícitos y nota "not matches"; lote con run, resultados paginados y advertencia de completitud; estado de proveedor degradado con `freshness_seconds` y ausencia explícita fuera de intervalo; búsquedas restringidas por tipo con citas. Ver [unit-tests.log](unit-tests.log).

## T04

`test_other_tenant_resources_are_indistinguishable_from_missing` (mismo código y mensaje), lote de otro tenant `NOT_FOUND`, `test_missing_scope_is_forbidden`, `test_identity_comes_only_from_the_environment` (scopes desconocidos, tenant vacío y roles inválidos rechazados), chunk de otro tenant ausente y chunk inyectado marcado `untrusted_instructions` con advertencia. Ver [unit-tests.log](unit-tests.log).

## T05

Cuatro argumentos inválidos (UUID mal formado, revisión 0, propiedad extra `tenant_id`, faltante) → `INVALID_ARGUMENT`; `TIMEOUT` retryable con backend lento (0.5 s vs 0.1 s); `DEPENDENCY_UNAVAILABLE` con backend caído; `RATE_LIMITED` a la cuarta llamada con límite 3; `max_in_flight == 2` con cinco llamadas simultáneas; truncamiento a un ítem completo bajo el límite con procedencia coherente; `approve_resolution`, `execute_approved_action` y `sql` → error de protocolo "Unknown tool"; auditoría con sujeto, tenant, hash SHA-256 de argumentos y sin el texto de la consulta. Ver [unit-tests.log](unit-tests.log).

## T06

`test_related_candidates_pagination_and_cursor_binding`: dos páginas cubren los dos candidatos sin repetir; cursor alterado y cursor de otra transacción → `INVALID_ARGUMENT`; tras cambiar el snapshot → `STALE_SNAPSHOT`. Ver [unit-tests.log](unit-tests.log).

## T07

`test_sql_backend_end_to_end_over_stdio` en [smoke.json](smoke.json): tenant nuevo con los datos v2 ingeridos y un run ejecutado; servidor lanzado por stdio con `--backend sql` y el rol `recon_mcp`; revisión `2025-11-25`; transacción propia correcta y la misma clave de `tenant-demo` → `NOT_FOUND`; contraparte por `same_reference`; lote con el run, 2 resultados y cursor; prov-alfa `degraded` el 2026-08-16; E17 → `alfa-error-codes@2` primero con cita `[alfa-error-codes@2#…]`; incidentes sólo de tipo incidente; exactamente 7 filas de auditoría escritas por el sujeto del servidor.

## T08

`test_generated_uid_matches_python_twin`, `test_mcp_role_reads_evidence` (sin superusuario/CREATEDB/CREATEROLE), nueve intentos denegados con `InsufficientPrivilege` (INSERT de lote, UPDATE de resultados y de conocimiento, DELETE de observaciones y auditoría, UPDATE de auditoría, SELECT de outbox y de artefactos, CREATE TABLE), `test_schema_matches_sqlalchemy_metadata` sin drift con `0004_mcp_read_model` y `migrate` idempotente (`M1-T08`). Ver [smoke.json](smoke.json).

## T09

Gate completo en [gate-all.log](gate-all.log).

El archivo del change se verificó con el gate estático posterior a `openspec archive` ([gate-static-post-archive.log](gate-static-post-archive.log): todos PASS, incluida la regla de trazabilidad para changes archivados).
