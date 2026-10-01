# Estrategia de pruebas — M9

Unit tests para exposición, alertas, propagación, parsing de DLQ, escáner y matriz de acceso. Integración contra PostgreSQL para latidos, snapshot, grants y revocación. Drills en el smoke y demo de trazas con Jaeger.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Propagación | `tests/unit/test_observability.py`: `traceparent` ida y vuelta, apagado por defecto, columna `trace_context` con default; demo `scripts/observability_demo.py`: una traza con los 4 servicios y sin atributos prohibidos (`evidence/tracing-demo.json`) |
| T02 | Métricas | Unit: rutas como plantillas (sin IDs), `unmatched`, fuentes caídas con `up 0`, etiquetas sin tenant. Integración `test_observability_store.py`: snapshot real. Smoke `M9-T04` |
| T03 | Reglas | Unit: archivo válido con runbooks existentes, sin alertas en estado sano, una alerta por falla parametrizada, política de series ausentes |
| T04 | Fault injection: caída | Smoke `M9-T05` (outage): con NATS y worker detenidos, el run queda `requested` y disparan las tres alertas. Tras recuperar se completa una vez, filas = conteos, un solo run, alertas limpias, re-run con igual snapshot y conteos |
| T05 | Fault injection: DLQ | Smoke `M9-T05` (dead letters): el veneno dispara `DeadLetters` y no se re-publica; se descarta, el agotado se re-publica, una copia duplicada no duplica efectos, la alerta se limpia y hay 3 entradas de auditoría `dlq.*` |
| T06 | Backup y restore | Smoke `M9-T06`: conteos y digest de auditoría coinciden; tiempos medidos |
| T07 | Runbooks | Unit: cada regla enlaza un runbook existente. Integración `test_revoke_command_of_the_runbook_is_audited`. Los comandos de DLQ, backup y alertas se ejecutan en T04–T06 |
| T08 | Secretos | `tests/unit/test_secret_scan.py` con canarios por patrón y rutas prohibidas; paso de gate `secrets` sobre toda la historia (`evidence/secret-scan.json`) |
| T09 | Acceso | `tests/unit/test_access_matrix.py`: 18 rutas × 5 roles, 401 sin token y 403 fuera del conjunto; integración: grants mínimos de `recon_app` en las tablas nuevas |

## Ejecución y evidencias

`uv run python scripts/gate.py all` y `uv run python scripts/observability_demo.py --out ...`. Evidencia en [evidence/](evidence/README.md).

## Stop condition

Sin despliegues, sin servicios externos y sin escáneres descargados. Las fallas inyectadas sólo afectan este proyecto Compose.
