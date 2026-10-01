# Estrategia de pruebas — M10

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Sesión reproducible | `scripts/demo.py seed` dentro del smoke `M10-T03`: 12 lotes y 44 pagos, resultados iguales a las etiquetas |
| T02 | Aislamiento | `M10-T03`: un run de otra sesión devuelve 404 y el listado de lotes contiene sólo los propios |
| T03 | Kill switch | Unit `tests/unit/test_kill_switch.py`: 503 `ai_disabled` sólo después de 401/403, un run no queda bloqueado, `recon_ai_enabled 0` y parsing de `APP_AI_ENABLED`. Vitest: mensaje en el dashboard. `M10-T03`: con el switch apagado, investigación 503 → caso → propuesta sin borrador → aprobación → run determinístico completo; al reactivarlo, investigación 202 |
| T04 | Revisión previa a publicar | `tests/unit/test_secret_scan.py` (rutas de perfil, `.demo/` prohibido), paso `policy` sobre el árbol, paso `secrets` sobre la historia, `scripts/license_inventory.py` (evidencia) |
| T05 | Documentación | Revisión de `walkthrough.md`, `results.md` y `datasets/README.md` contra la evidencia enlazada; gate completo |

## Ejecución y evidencias

`uv run python scripts/gate.py all`, `scripts/demo.py resources` y `scripts/license_inventory.py --json`. Evidencia en [evidence/](evidence/README.md).

## Stop condition

Nada se publica, despliega ni sube. Las decisiones del propietario quedan documentadas.
