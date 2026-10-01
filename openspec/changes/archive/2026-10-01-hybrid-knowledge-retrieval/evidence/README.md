# Evidencia — hybrid-knowledge-retrieval (M3)

Ejecutada el 2026-10-01 en Windows 11 (Docker 29.8.1, Compose 5.5.1, linux/amd64), rama `m3-hybrid-knowledge-retrieval` con cambios sin commitear (el smoke registra `dirty: true`). Toda la evidencia es **MEASURED** con alcance local, corpus sintético pequeño y embeddings de hashing **no semánticos**; no es un benchmark ni generaliza a datos reales. El CI remoto no se ejecutó (bloqueo de facturación de GitHub, AC06 de M0).

Archivos:

- [gate-all.log](gate-all.log): `uv run python scripts/gate.py all`, todos los pasos PASS; 174 tests unitarios; smoke 15/15.
- [unit-tests.log](unit-tests.log): `pytest -v tests/unit/test_knowledge.py` (15 passed).
- [smoke.json](smoke.json): reporte del smoke con los tests de integración (14 de M3 en `test_knowledge_retrieval.py`) y los pasos `M3-T04`/`M3-T07`.
- [retrieval-eval.json](retrieval-eval.json): reporte completo de la evaluación (métricas por modo y split, objetivo por umbral en dev, fallos).

Nota operativa: una corrida intermedia dejó 6 documentos de prueba con alcance `global` en el volumen local; se revocaron (no se borraron) con el rol runtime y auditoría (`maintainer-cleanup`, correlación `m3-cleanup`), y los tests pasaron a usar un tenant único por corrida para no contaminar otras suites. El evaluador cuenta como violación cualquier documento fuera del corpus evaluado.

## T01

`test_corpus_is_valid_versioned_and_manifested` (17 documentos con estados published/draft/revoked, dos versiones de `alfa-error-codes`, manifest idéntico al regenerado, `data_origin: SYNTHETIC`), `test_queries_point_to_existing_evidence_units_without_split_leakage` (38 queries, 8 sin respuesta, todas las unidades existen, ninguna familia en dos splits), seis casos de metadatos inválidos, y número tipo tarjeta (generado en runtime) y cabecera de clave privada rechazados. Ver [unit-tests.log](unit-tests.log).

## T02

Chunks por sección con `intro`, `E17` extraído, IDs determinísticos, flag de instrucciones en `alfa-status-faq@1#nota-del-portal` y no en `#estado-pending`; sección larga dividida con overlap sin romper la lista numerada y con una sola unidad canónica; embeddings determinísticos, 256 dims, norma 1, similitud léxica mayor para textos parecidos y manifest `semantic: false`. Ver [unit-tests.log](unit-tests.log).

## T03

RRF con valores exactos (`1/61 + 1/62`), deduplicación dentro de una rama y desempate por ID; reglas de abstención (sin evidencia, código no documentado, cobertura baja); oráculo de autorización (versión superada, otro tenant, ACL supervisor, borrador, revocado, incidente no publicado a la fecha) e intervalo de Wilson. Ver [unit-tests.log](unit-tests.log).

## T04

PostgreSQL real (rol runtime) en [smoke.json](smoke.json): `test_publication_is_idempotent_and_versions_are_immutable` (17 `unchanged`, versión alterada → `KnowledgeConflictError`), `test_failed_embedding_leaves_previous_version_active` (el fallo en el primer embedding deja sólo la versión 1, que sigue recuperable y no aparece para otro tenant), `test_revocation_removes_from_every_branch` (ningún modo la devuelve y la cita deja de resolverse). Paso `M3-T04`: dos re-ejecuciones de `knowledge-ingest` con `published: 0, unchanged: 17`.

## T05

`test_rg02_as_of_selects_the_applicable_version` (con `as_of` 2026-03-01 el primer resultado es `alfa-error-codes@1#e17-…` y no aparece la v2; el incidente INC-0815 no se recupera antes de su publicación en ningún modo), `test_rg04_other_tenant_content_is_never_exposed` (ningún modo devuelve el runbook de `tenant-other` a `tenant-demo`; para `tenant-other` sí; su chunk no se resuelve como cita para `tenant-demo`), `test_acl_draft_and_revoked_are_hard_filters`. Ver [smoke.json](smoke.json).

## T06

`test_rg01_error_code_lookup_returns_current_document` (E17 vigente primero, sin v1), `test_rg03_abstains_without_evidence` (Z99 y tasa EUR/JPY → abstención con motivo y sin citas), `test_untrusted_instructions_are_returned_as_flagged_data` (advertencia `untrusted_instructions:<chunk>`), `test_index_stores_versioned_embedding_metadata` (todo el índice en `hashing-ngram`/`v1`/256). Ver [smoke.json](smoke.json).

## T07

Paso `M3-T07` y [retrieval-eval.json](retrieval-eval.json). Configuración: RRF k=60, 20 candidatos por rama, top 5, búsqueda vectorial exacta, umbral de cobertura 0.6 elegido en `dev` (el mismo para los tres modos; con 0.4 la abstención en dev era 0.75). Resultados (dev: 17 respondibles + 4 sin respuesta; holdout: 13 + 4):

| Modo | Split | precision@5 | recall@5 | MRR | Abstención correcta (IC 95 %) | Abstenciones falsas | Violaciones ACL | p95 ms |
|---|---|---|---|---|---|---|---|---|
| lexical | dev | 0.259 | 0.882 | 0.926 | 1.00 (0.51–1.00) | 0 | 0 | 3.95 |
| lexical | holdout | 0.235 | 0.923 | 0.923 | 0.50 (0.15–0.85) | 1 | 0 | 5.13 |
| vector | dev | 0.259 | 0.853 | 0.794 | 1.00 (0.51–1.00) | 0 | 0 | 1.81 |
| vector | holdout | 0.231 | 0.923 | 0.833 | 0.75 (0.30–0.95) | 1 | 0 | 2.30 |
| híbrido | dev | 0.271 | 0.912 | 0.971 | 1.00 (0.51–1.00) | 0 | 0 | 3.09 |
| híbrido | holdout | 0.231 | 0.923 | 0.923 | 0.50 (0.15–0.85) | 1 | 0 | 3.50 |

Lectura honesta: el híbrido tiene el mejor MRR en dev, pero en holdout no supera al lexical; con n=4 queries sin respuesta por split los intervalos son muy anchos. precision@5 está acotada por diseño (top-5 fijo con 1–2 unidades relevantes por query). Fallos del híbrido: q06 y q09 (recupera sólo una de dos unidades relevantes), q13 (abstención falsa), q23 (recupera una de dos), q37 y q38 (no abstiene: "contraseña del portal de administración" coincide léxicamente con el texto de prompt injection y "promoción sin comisión" con E21). No se alcanzan los objetivos EXPECTED de docs/07 (precision ≥ 0.80, abstención ≥ 0.95); no son criterio de aceptación de M3. Latencias medidas dentro de la red Compose sobre un índice con los 56 chunks del corpus (más documentos de prueba de otros tenants, excluidos por los filtros).

## T08

`test_schema_matches_sqlalchemy_metadata` sin drift con `0003_knowledge` (incluido el tipo `vector(256)` reflejado), `migrate` idempotente (`M1-T08`) y `test_runtime_role_cannot_rewrite_knowledge` (DELETE de documentos y chunks, UPDATE de ACL y de contenido → `InsufficientPrivilege`). Ver [smoke.json](smoke.json).

## T09

Gate completo en [gate-all.log](gate-all.log), incluido `check_traceability` y `openspec validate --all --strict`.

El archivo del change se verificó con el gate estático posterior a `openspec archive` ([gate-static-post-archive.log](gate-static-post-archive.log): todos PASS, incluida la regla de trazabilidad para changes archivados).
