## Why

La investigación de excepciones (M5) necesita contexto verificable: runbooks, códigos de error, documentación de proveedores e incidentes, con versión, vigencia y permisos. Sin una base de conocimiento con filtros duros, citas resolubles y abstención explícita, cualquier agente tendería a rellenar huecos o a citar documentos ajenos, obsoletos o revocados. M3 entrega esa base y mide sus baselines antes de que exista un agente que la use.

## What Changes

- **Corpus sintético `knowledge-v1`:** 17 documentos versionados (ES/EN) de dos proveedores ficticios, con front matter validado (tenant, ACL, tipo, idioma, vigencia, publicación, estado de revisión), manifest con hashes y 38 queries etiquetadas por familia y split (`dev`/`holdout`), incluidas queries sin respuesta, de otro tenant, con ACL restringida, sobre borradores, revocados y un documento con prompt injection deliberado.
- **Chunking `chunking/v1`:** por secciones `##`, división con overlap sólo en secciones largas sin romper listas ni tablas, IDs derivados de documento/versión/localizador/hash y unidades de evidencia canónicas.
- **Embeddings locales `hashing-ngram/v1`:** hashing firmado de palabras y trigramas, 256 dimensiones, normalización L2, sin descargas; declarados como no semánticos.
- **Almacenamiento en PostgreSQL + pgvector:** migración `0003_knowledge`, `tsvector` por idioma con índice GIN, códigos de error exactos, `vector(256)` con búsqueda exacta (sin ANN), publicación atómica por versión, revocación auditada y privilegios mínimos.
- **Retrieval híbrido:** FTS + lookup exacto de códigos + vector, fusionados con RRF (k=60), top 5; los mismos filtros duros en todas las ramas; abstención explícita; contenido con instrucciones marcado como no confiable; citas `[document@version#chunk]` resolubles sólo dentro del universo autorizado.
- **Evaluación:** baselines lexical/vector/híbrido con precision@5, recall@5, MRR, abstención en queries sin respuesta, violaciones de ACL y latencia; umbral de abstención ajustado sólo en `dev`, reportado en `holdout`; etiquetado MEASURED sobre datos sintéticos.

## Capabilities

### New Capabilities

- `hybrid-knowledge-retrieval`: base de conocimiento sintética, versionada y con permisos, con recuperación híbrida, abstención y evaluación reproducible.

### Modified Capabilities

Ninguna. El engine runtime agrega `public` al `search_path` después de `recon` sólo para resolver el tipo y los operadores de pgvector (nadie puede crear objetos en `public`).

## Impact

Nuevo paquete `packages/knowledge` (`recon_knowledge`), tipo `Vector` en `recon_store`, migración `0003_knowledge`, job Compose `knowledge-ingest`, corpus en `datasets/synthetic/knowledge-v1` (copiado a la imagen runtime), pasos de smoke `M3-T04`/`M3-T07`. Sin dependencias nuevas de terceros.

Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md) (D04: embeddings determinísticos locales; FTS + vector + RRF reales en pgvector).

## Non-goals

Modelos de embeddings semánticos, reranker, ANN/HNSW, UI de curaduría, ingestion de fuentes externas, uso del corpus por agentes (M5) y exposición por MCP (M4). Las métricas no son de calidad semántica ni generalizan fuera del corpus sintético.
