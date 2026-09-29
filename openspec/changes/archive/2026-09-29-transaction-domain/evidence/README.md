# Evidencia — transaction-domain (M1)

Ejecutada el 2026-09-29 en Windows 11 (Docker 29.8.0, Compose v2), rama `m1-transaction-domain` con cambios sin commitear al momento de la corrida (el smoke registra `dirty: true`). Toda la evidencia es **MEASURED** con alcance local y datos sintéticos; no es benchmark.

Archivos:

- [gate-all.log](gate-all.log): `uv run python scripts/gate.py all` completo (lock, lint, types, test, policy, trace, openspec, negative, smoke), todos PASS.
- [unit-tests.log](unit-tests.log): `pytest -v` de los tests unitarios de M1 (50 passed).
- [smoke.json](smoke.json): reporte del smoke Compose, incluye la lista de tests de integración ejecutados en el contenedor (20 passed, 11 de M1).

## T01

Dinero exacto: `tests/unit/test_money.py` (roundtrip decimal con Hypothesis, suma/resta inversas, rechazo de float/bool/NaN/Infinity, precisión excesiva `10.005`, overflow de 64 bits y cross-currency). Ver [unit-tests.log](unit-tests.log).

## T02

Observaciones: `tests/unit/test_observation.py` (inmutabilidad, timestamps naive rechazados, offset y UTC conservados, campos inválidos, scope de comparación, hash canónico, test AST sin imports de infraestructura en `recon_domain`). Ver [unit-tests.log](unit-tests.log).

## T03

Revisiones: `test_revision_outcomes` y la propiedad `test_replaying_a_stored_revision_never_creates_an_effect` en [unit-tests.log](unit-tests.log); en PostgreSQL real, `test_ingest_outcomes_and_effects` en [smoke.json](smoke.json).

## T04

Lotes: `test_batch_window_is_half_open`, `test_batch_admits_only_its_scope`, `test_batch_closure_uses_cutoff` y `test_invalid_batches_are_rejected` en [unit-tests.log](unit-tests.log).

## T05

Mappings: `test_mappings_translate_known_values_and_reject_unknown` en [unit-tests.log](unit-tests.log).

## T06

Fixtures: `tests/unit/test_synthetic_dataset.py` regenera `datasets/synthetic/transactions-v1` y compara archivos y manifest (content hash `f4195e3b…43b6`), verifica determinismo por semilla, los 11 escenarios etiquetados, `data_origin: SYNTHETIC` y el scan de secretos/PAN sin hallazgos.

## T07

Persistencia atómica (PostgreSQL 17.11 real, rol runtime): `test_ingest_outcomes_and_effects` (3 filas, 3 eventos outbox, 4 auditorías: el replay no escribe y el conflicto sólo audita), `test_failed_transaction_leaves_no_partial_effects`, `test_concurrent_ingest_of_same_key_creates_one_row` (4 hilos → 1 CREATED + 3 DUPLICATE) y `test_database_rejects_invalid_rows`. Ver [smoke.json](smoke.json).

## T08

Migraciones y privilegios: `test_schema_matches_sqlalchemy_metadata` (sin drift entre Core y Alembic), los seis casos de `test_runtime_role_cannot_rewrite_history` (InsufficientPrivilege) y el paso smoke `M1-T08 alembic migrate idempotent re-run` (dos ejecuciones en `0001_transaction_domain`). Ver [smoke.json](smoke.json) y [gate-all.log](gate-all.log).

## T09

Gate completo verde y `check_traceability`/`openspec validate --all --strict` en [gate-all.log](gate-all.log). El archivo del change se verifica con el gate estático posterior al `openspec archive` ([gate-static-post-archive.log](gate-static-post-archive.log): todos PASS, incluida la regla de trazabilidad para changes archivados).
