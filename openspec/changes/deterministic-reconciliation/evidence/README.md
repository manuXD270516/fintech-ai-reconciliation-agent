# Evidencia — deterministic-reconciliation (M2)

Ejecutada el 2026-10-01 en Windows 11 (Docker 29.8.1, Compose 5.5.1, linux/amd64), rama `m2-deterministic-reconciliation` con cambios sin commitear al momento de la corrida (el smoke registra `commit: e1fd40b`, `dirty: true`). Toda la evidencia es **MEASURED** con alcance local y datos sintéticos; no es benchmark de rendimiento. El CI remoto no se ejecutó (bloqueo de facturación de GitHub, ver AC06 de M0).

Archivos:

- [gate-all.log](gate-all.log): `uv run python scripts/gate.py all` (lock, lint, types, test, policy, trace, openspec, negative, smoke), todos PASS; 159 tests unitarios.
- [unit-tests.log](unit-tests.log): `pytest -v` de los tests unitarios de M2 (51 passed).
- [smoke.json](smoke.json): reporte del smoke Compose (13/13 PASS) con la lista de 35 tests de integración ejecutados dentro de la red Compose contra PostgreSQL 17 + pgvector y NATS JetStream reales.

## T01

Ingestion y cuarentena: `test_bad_rows_are_quarantined_without_blocking_good_rows` (10 códigos/casos: precisión `10.005`, importe inválido, estado y operación sin mapping, tenant y proveedor ajenos, campo faltante, timestamp naive, revisión 0, moneda no soportada), `test_valid_row_maps_vocabulary_and_keeps_raw_hash`, `test_wrong_header_rejects_whole_artifact`. Ver [unit-tests.log](unit-tests.log).

## T02

Reglas `rules/v1`: tolerancia cero (`-1` unidad menor ya es `AMOUNT_MISMATCH`), importe+hora sin referencia no hacen match, empate débil conservado como `weak_ambiguous` con alternativas `(2, 3)`, `WAITING_SOURCE` antes del cutoff o sin completitud y `MISSING_EXTERNAL` después, aislamiento de alcance, `PROCESSING_ERROR` por cuarentena, independencia del orden de entrada; RC06 (USD vs BOB nunca se comparan), RC11 (23:30 −04:00 y 03:30 Z caen en la misma ventana) y RC12 (refund parcial y liquidación neta no se fuerzan; diferencia `-300`). Ver [unit-tests.log](unit-tests.log).

## T03

Oráculo: el pipeline puro reproduce las 44 etiquetas de `transactions-v2` y es determinístico; con ventana abierta todos los faltantes son `WAITING_SOURCE`; v1 queda congelado y difiere sólo en pares enlazados. Benchmark sintético: 550 pagos (11 escenarios × 50) con semillas 1, 7 y 20260929, 0 discrepancias contra etiquetas y conjunto de EXACT predichos idéntico al gold (cero falsos EXACT observados en estos datos). Ver [unit-tests.log](unit-tests.log).

## T04

PostgreSQL real (rol runtime), en [smoke.json](smoke.json): `test_dataset_end_to_end_matches_oracle` (ingesta de v2 con 8 filas en cuarentena y 4 duplicados de transporte, replay de los 4 artefactos sin efectos, 12 lotes, cada evento de run procesado una vez y la segunda entrega `duplicate`, resultados iguales al oráculo), `test_rerun_creates_new_version_and_keeps_previous`, `test_rc10_late_arrival_creates_new_run_and_keeps_previous` (snapshot hash distinto, run 1 intacto, más EXACT en run 2), `test_idempotency_key_reuse_with_other_content_conflicts`, `test_tenant_isolation_on_reads`.

## T05

Unit: `test_ingest_subject_carries_identity`, cuatro envelopes malformados como `PoisonMessageError` antes de tocar almacenamiento y `test_malformed_run_event_is_poison`. Integración con el servicio `worker` real: `test_events_are_ingested_once_by_the_worker` (6 eventos + 2 reentregas → 6 artefactos), `test_body_cannot_override_subject_tenant` (tenant del cuerpo distinto → `scope_violation`), `test_poison_event_goes_to_dead_letter_stream` (mensaje en `recon.dlq.observation-ingestor` con razón `poison:`).

## T06

`tests/unit/test_auth.py`: token válido → principal; expirado, emisor/audiencia incorrectos, firma ajena, `alg=none` y claims inválidos rechazados; roles desconocidos descartados; 401 sin token, 403 por rol antes de tocar almacenamiento, 503 fail-closed sin verificador. `tests/unit/test_scope.py`: catálogo exacto de rutas y métodos, sin palabras de pago/agente. Ver [unit-tests.log](unit-tests.log).

## T07

Paso smoke `M2-T07` en [smoke.json](smoke.json): desde el host, 4 artefactos por HTTP (la base persistente ya los tenía de corridas previas, por lo que el recibo es `replayed: true` con los mismos conteos: 22+22 aceptadas, 18+18 aceptadas y 4+4 en cuarentena), 403 para un analista que intenta ingerir, 401 sin token, 12 lotes con completitud y runs `202` ejecutados por el worker vía outbox → JetStream; 44/44 pagos coinciden con el oráculo; todos los runs completos en 0.93 s.

## T08

`test_schema_matches_sqlalchemy_metadata` (sin drift con `0002_reconciliation`), paso smoke `M1-T08` (dos ejecuciones de `migrate` terminan en la misma revisión) y 13 casos de `test_runtime_role_cannot_rewrite_history`, 7 de ellos sobre tablas M2 (UPDATE/DELETE en artefactos, cuarentena, resultados, runs e inbox → `InsufficientPrivilege`). Ver [smoke.json](smoke.json).

## T09

`test_rc01_deterministic_path_has_no_model_or_http_client`: AST de `recon_domain`, `recon_store` y `recon_worker` sin imports de `httpx`, `openai`, `anthropic`, `ollama`, `requests`, `urllib` ni paquetes de agentes. Gate completo en [gate-all.log](gate-all.log).
