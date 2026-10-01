# Estrategia de pruebas — M2

Unitarias puras para parser y reglas, oráculo etiquetado, integración contra PostgreSQL y JetStream reales en el contenedor smoke y un E2E HTTP desde el host. Sin modelos ni red externa.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Ingestion y cuarentena | Parser CSV: cada código de rechazo, filas válidas no bloqueadas, encabezado inválido rechaza todo, mapping de vocabulario y `raw_hash` estable (`tests/unit/test_ingestion_and_rules.py`) |
| T02 | Reglas `rules/v1` | Tolerancia cero, importe+hora no bastan, empates ambiguos, waiting vs missing, alcance, processing error, independencia del orden; RC06/RC11/RC12 (`test_ingestion_and_rules.py`, `test_reconciliation_catalog.py`) |
| T03 | Oráculo y benchmark | Dataset v2 reproducido exactamente (44 pagos), determinismo, ventana abierta, v1 congelado; benchmark de 550 pagos con 3 semillas sin falsos EXACT (`test_reconciliation_oracle.py`, `test_reconciliation_catalog.py`) |
| T04 | Persistencia de runs | PostgreSQL real: dataset completo vía store + handler del worker igual al oráculo, replay de artefactos, rerun versionado, llegada tardía RC10, conflicto de clave, aislamiento de tenant (`tests/integration/test_reconciliation_flow.py`, `test_event_ingestion.py`) |
| T05 | Worker, eventos y DLQ | Subjects con identidad, eventos malformados como poison sin tocar DB (unit); eventos reales en JetStream ingeridos una sola vez por el worker, tenant del subject prevalece, poison en `RECON_DLQ` (integration) |
| T06 | API, auth y catálogo | JWT válido/expirado/emisor/audiencia/`alg=none`/clave ajena, 401/403 antes de almacenamiento, fail-closed sin verificador, catálogo exacto de rutas (`test_auth.py`, `test_scope.py`) |
| T07 | E2E Compose | Smoke `M2-T07`: ingest HTTP de v2, lotes, completitud y runs vía outbox → NATS → worker; resultados iguales al oráculo; 403 y 401 verificados |
| T08 | Migración y privilegios | Sin drift Core vs Alembic (`0002`), `migrate` idempotente, rol runtime sin UPDATE/DELETE en tablas M2 (`test_store.py`) |
| T09 | Ausencia de IA y gate | AST sin clientes de modelos/HTTP en dominio, store y worker (RC01); `scripts/gate.py all` y trazabilidad |

## Ejecución y evidencias

`uv run python scripts/gate.py all`: T01–T03, T05 (unit), T06 y T09 en `test`; T04, T05 (integration) y T08 dentro del contenedor smoke; T07 como paso del smoke. Evidencia en [evidence/](evidence/README.md). Toda métrica es MEASURED sobre datos sintéticos.

## Stop condition

M2 no crea casos de investigación, retrieval, tools MCP ni llamadas a modelos.
