# Estrategia de pruebas — M4

Pruebas de contrato con cliente MCP real en memoria y por stdio (subprocess) sobre un backend de fixture; integración con el backend SQL y el rol `recon_mcp` dentro de la red Compose. Sin modelos ni red externa.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Discovery y schemas | Exactamente seis tools en orden, `readOnlyHint`, `destructiveHint=false`, `outputSchema` presente, todo objeto con `additionalProperties: false`, sin campos de identidad ni nombres de escritura (`tests/unit/test_mcp_server.py`) |
| T02 | Protocolo y transportes | Versión negociada `2025-11-25` y `server_info`; servidor real por stdio como subprocess con backend de fixture (mismo archivo) |
| T03 | Semántica de tools | Revisión vigente e histórica con advertencia, candidatos relacionados con criterios explícitos y nota "not matches", lote con run, resultados paginados y advertencia de completitud, estado de proveedor por intervalo y ausencia explícita, búsquedas por tipo con citas (mismo archivo) |
| T04 | Autorización | Otro tenant ≡ inexistente (`NOT_FOUND`, mismo mensaje), lote ajeno, scope faltante `FORBIDDEN`, identidad sólo desde el entorno, chunk de otro tenant nunca devuelto, contenido inyectado marcado (mismo archivo) |
| T05 | Errores y límites | Argumentos inválidos/extra, `TIMEOUT` retryable, `DEPENDENCY_UNAVAILABLE`, `RATE_LIMITED`, máximo 2 en vuelo con 5 llamadas, truncamiento por ítems completos bajo el límite, tools desconocidas o de escritura como error de protocolo, auditoría con hash y sin argumentos (mismo archivo) |
| T06 | Paginación | Dos páginas completas, cursor alterado y de otros argumentos `INVALID_ARGUMENT`, cursor tras cambio de snapshot `STALE_SNAPSHOT` (mismo archivo) |
| T07 | SQL por stdio | En la red Compose: tenant nuevo con datos v2, run ejecutado, conocimiento y estado de proveedor; subprocess `--backend sql` con el rol `recon_mcp`: seis tools, transacción propia y ajena, relacionadas, lote paginado, estado degradado, E17 vigente con cita, incidentes, 7 auditorías escritas (`tests/integration/test_mcp_sql.py`) |
| T08 | Rol y migración | `transaction_uid` SQL = gemelo Python; rol sin superusuario; writes, lecturas de outbox/artefactos y CREATE denegados; drift `0004` y `migrate` idempotente (`test_mcp_sql.py`, `test_store.py`, smoke `M1-T08`) |
| T09 | Gate | `scripts/gate.py all` y trazabilidad |

## Ejecución y evidencias

`uv run python scripts/gate.py all`. Evidencia en [evidence/](evidence/README.md).

## Stop condition

M4 no conecta ningún modelo al servidor ni agrega write tools.
