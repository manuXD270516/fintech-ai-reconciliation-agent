# Estrategia de pruebas — M1

Pruebas de propiedades y negativas para invariantes del dominio; integración real contra PostgreSQL en el contenedor smoke. Sin modelos ni red externa.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Dinero exacto | Hypothesis: roundtrip decimal y suma/resta inversas; rechazo de floats, bool, NaN, precisión excesiva, overflow y cross-currency (`tests/unit/test_money.py`) |
| T02 | Observaciones | Inmutabilidad, timestamps naive rechazados, offset/UTC, campos inválidos, scope de comparación, hash canónico y pureza del paquete de dominio (`tests/unit/test_observation.py`) |
| T03 | Revisiones | Tabla de resultados y propiedad: replay de revisión almacenada nunca persiste (`tests/unit/test_revisions_batches_mappings.py`) |
| T04 | Lotes | Ventana semiabierta, admisión por alcance, cutoff y lotes inválidos (mismo archivo) |
| T05 | Mappings | Traducción conocida y rechazo de valores/proveedores desconocidos (mismo archivo) |
| T06 | Fixtures | Regeneración idéntica al dataset versionado, determinismo por semilla, escenarios etiquetados y secret/PAN scan (`tests/unit/test_synthetic_dataset.py`) |
| T07 | Persistencia atómica | PostgreSQL real: resultados de ingesta y efectos, rollback sin efectos parciales, concurrencia de la misma clave, constraints (`tests/integration/test_store.py`) |
| T08 | Migraciones y privilegios | Drift esquema vs metadata, migrate idempotente (smoke `M1-T08`), rol runtime sin UPDATE/DELETE/CREATE |
| T09 | Trazabilidad y gate | `scripts/gate.py all` completo, incluido `openspec validate --all --strict` y `check_traceability` |

## Ejecución y evidencias

`uv run python scripts/gate.py all` ejecuta unitarios (T01–T06) y el smoke Compose, que corre `tests/integration` en el contenedor (T07/T08) y el re-run de `migrate`. Evidencia en [evidence/](evidence/README.md). Un T omitido o fallido deja su criterio en PENDING/FAIL.

## Stop condition

M1 no crea endpoints, reglas de matching ni ingestion de archivos. Cualquier prueba de M2 queda fuera.
