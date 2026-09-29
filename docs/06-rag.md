# Diseño RAG híbrido

## Alcance y autoridad

Corpus exclusivamente sintético en la demo: procedimientos operativos, documentación de dos proveedores ficticios, códigos de error, runbooks e incidentes históricos. No indexar datos de tarjetas ni el catálogo transaccional para hacer matching semántico. Datos del caso se consultan con tools de dominio; RAG explica contexto y procedimientos, no decide que se movió dinero.

## Ingestion y versionado

Flujo: fuente allowlisted → validación y escaneo de contenido → normalización → hash/dedupe → metadatos → chunking → embeddings → staging → publicación atómica de versión → índices disponibles. Un fallo de embeddings conserva la versión anterior activa; documento parcialmente indexado no se publica. Revocación afecta recuperación, citas visibles y cachés. Original y localizadores se preservan en artefacto versionado.

Metadatos de documento: `document_id`, `version`, `tenant_scope`, `acl`, `provider_id`, `document_type`, `title`, `language`, `source_uri`, `content_hash`, `effective_from/to`, `published_at`, `ingested_at`, `review_status`, `synthetic`, `supersedes`. Metadata de chunk: `chunk_id`, `section_path`, `ordinal`, `start/end_locator`, `token_count`, `error_codes[]`, `content_hash`, `embedding_model`, `embedding_revision`, `dimensions`, `index_version`.

Validez del contenido y tiempo de ingestión se guardan por separado. Incidentes posteriores al momento que intenta reconstruir un caso no pueden servir como evidencia histórica disponible entonces. ACL/tenant vienen del contexto autenticado; sólo corpus explícitamente global se comparte.

## Chunking

Priorizar límites semánticos de títulos, pasos, tablas y definiciones de error. Valor inicial **EXPECTED**: 400–700 tokens con overlap de 60–100; pasos numerados y tablas pequeñas permanecen juntos. Tablas grandes repiten encabezados y preservan localizador de filas. Separar secciones largas sin mezclar proveedores ni versiones. Mantener relación parent/child para recuperar un encabezado o procedimiento completo si cabe en presupuesto.

Medir alternativas de tamaño en dev. El chunk_id se deriva de documento/versión/localizador/hash; cambiar estrategia produce index_version nueva. No duplicar el mismo texto en el contexto por el overlap.

## Embeddings y almacenamiento

Adaptador de embeddings con modelo, revisión, dimensión, tokenizer y normalización fijados en un manifest. Elegir modelo multilingüe por evaluación en español/inglés y costo reproducible en M3; ninguna calidad ni dimensión concreta se presume ahora. No mezclar espacios vectoriales en una columna/index activo; cambio de modelo implica reindexado completo en staging y activación después de evals. Fixtures con embeddings falsos prueban plumbing, nunca calidad semántica.

PostgreSQL almacena texto y `tsvector`; pgvector almacena vectores. Baseline inicial de vector search exacto con cosine distance para corpus pequeño. HNSW sólo si una medición demuestra necesidad, comparando resultados contra búsqueda exacta. pgvector advierte que filtros con índices aproximados pueden reducir resultados; verificar recall autorizado por tenant/proveedor, ajustar escaneo o partición y no recuperar fuera de ACL como fallback. [Documentación pgvector](https://github.com/pgvector/pgvector).

## Retrieval híbrido

1. Extraer de campos estructurados provider, error_code, idioma y fecha; no dejar que el modelo invente filtros de identidad.
2. Aplicar tenant/ACL, versión publicada y vigencia como filtros duros en todas las ramas.
3. Búsqueda lexical con PostgreSQL FTS; lookup exacto separado para IDs/códigos de error, que tokenización lingüística podría alterar.
4. Búsqueda semántica sobre el mismo universo autorizado. Configurar FTS por idioma; mantener códigos en campos exactos.
5. Recuperar inicialmente hasta 20 lexical + 20 vector (**EXPECTED**), unir/deduplicar y combinar con RRF: suma de `1 / (60 + rank)` por rama. No sumar scores crudos incompatibles.
6. Devolver top 5 como baseline; reranker opcional sólo si mejora el holdout bajo presupuesto. Ajustar constantes en dev, jamás en test.
7. No-result, evidencia conflictiva o fuera de vigencia se devuelve explícitamente. No relajar ACL, provider o fecha para llenar top-k.

## Context construction y citations

Context builder arma: instrucciones de autoridad → snapshot factual del caso → pregunta → fragmentos delimitados como datos no confiables → contradicciones/gaps → contrato de respuesta. Presupuesto inicial: hasta 6000 tokens de contexto por llamada, respetando además el presupuesto total del run. Priorizar fuentes aplicables y diversidad; truncar con indicador visible, sin romper localizadores.

Formato de cita: `[document_id@version#chunk_id]` y localizador de sección/página/fila. Evidencia transaccional usa `[observation_id@revision]`. Resolver referencia contra repositorio autorizado y verificar que el fragmento respalda el claim; no aceptar URLs inventadas como citas. Mostrar tanto fecha efectiva como fecha recuperada. Si fuentes se contradicen, exponer ambas y la política de precedencia, o abstenerse si ésta no resuelve el conflicto.

Un runbook puede decir “en error E17, revisar captura”; no autoriza a ejecutar acciones ni cambia la política del agente. Tratar instrucciones incrustadas (“ignora permisos”, “envía el token”) como contenido no confiable. Las herramientas y permisos vienen del servidor, no del documento recuperado.

## Retrieval evals

Dataset de queries con conjuntos de evidencia relevante versionada y queries sin respuesta. Medir precision@5, recall@5, MRR/nDCG opcionales, exactitud de códigos, soporte de citas, recall después de ACL y tasa de abstención correcta. Evaluar lexical-only, vector-only e híbrido con mismo corpus, filtros y split. Calcular relevancia a nivel de unidad de evidencia canónica para que chunks solapados no inflen recall. Latencia incluye query embedding, SQL, fusión y reranking. Plan completo en [evals](07-evals.md).
