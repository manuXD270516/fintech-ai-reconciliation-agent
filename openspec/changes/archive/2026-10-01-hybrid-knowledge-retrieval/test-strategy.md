# Estrategia de pruebas — M3

Unitarias sin base de datos para el contrato del corpus, chunking, embeddings y política de retrieval; integración contra PostgreSQL 17 + pgvector reales en el contenedor smoke; evaluación MEASURED en el smoke. Sin modelos, descargas ni red externa.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Corpus y manifest | 17 documentos válidos, manifest regenerado idéntico, metadatos inválidos rechazados, número tipo tarjeta y clave privada rechazados, queries apuntan a unidades existentes y sin fuga de familias entre splits (`tests/unit/test_knowledge.py`) |
| T02 | Chunking y embeddings | Secciones, códigos extraídos, flags de instrucciones, IDs determinísticos, división con overlap sin romper listas; embeddings determinísticos, L2=1, 256 dims, similitud léxica, manifest no semántico (mismo archivo) |
| T03 | Política de retrieval | RRF por rangos (valores exactos y desempate), reglas de abstención, cobertura, oráculo de autorización y Wilson (mismo archivo) |
| T04 | Publicación y revocación | PostgreSQL real: republicar = no-op, versión alterada = conflicto, fallo de embeddings sin versión parcial y con la anterior activa, revocación en todas las ramas y en citas (`tests/integration/test_knowledge_retrieval.py`); smoke `M3-T04` re-ejecuta `knowledge-ingest` (17 unchanged) |
| T05 | Filtros duros | RG02 por `as_of` (versión aplicable, incidente no publicado), RG04 sin exposición entre tenants en los tres modos y cita no resoluble, ACL por rol, borrador y revocado nunca devueltos (mismo archivo) |
| T06 | Comportamiento híbrido | RG01 (E17 vigente primero), RG03 (abstención sin citas), chunk con instrucciones devuelto con advertencia, metadatos de embedding versionados (mismo archivo) |
| T07 | Evaluación | Smoke `M3-T07`: `python -m recon_knowledge evaluate` en el stack; reporte JSON por modo y split; cero violaciones de ACL y cero familias filtradas como condición del paso |
| T08 | Migración y privilegios | Drift Core vs Alembic con `0003_knowledge`, `migrate` idempotente, rol runtime sin DELETE/UPDATE de contenido (`test_store.py`, `test_knowledge_retrieval.py`) |
| T09 | Gate | `scripts/gate.py all` y trazabilidad |

## Ejecución y evidencias

`uv run python scripts/gate.py all`. Evidencia en [evidence/](evidence/README.md). Las métricas de T07 son MEASURED sobre un corpus sintético pequeño con embeddings no semánticos; no se comparan con los objetivos EXPECTED de docs/07 como logro.

## Stop condition

M3 no expone tools MCP ni construye contexto para un modelo.
