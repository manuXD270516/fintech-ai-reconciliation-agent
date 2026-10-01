## ADDED Requirements

### Requirement: RF-01 Validated versioned synthetic corpus

El corpus SHALL estar versionado con manifest (origen `SYNTHETIC`, hashes por archivo y hash de contenido) y cada documento MUST declarar `document_id`, versión, alcance de tenant, ACL, tipo, idioma, vigencia, fecha de publicación y estado de revisión válidos. Un documento con números tipo tarjeta o material de claves MUST rechazarse; un texto con instrucciones dirigidas al modelo MUST conservarse marcado como no confiable.

#### Scenario: Card-like number in a document
- **WHEN** un documento contiene un número que pasa Luhn con 13 a 19 dígitos
- **THEN** la carga del corpus falla con un error identificable

#### Scenario: Prompt injection in provider content
- **WHEN** una sección contiene "ignora todas las instrucciones anteriores"
- **THEN** su chunk queda marcado `flagged_instructions` y se devuelve con advertencia, nunca como instrucción

### Requirement: RF-02 Deterministic heading-aware chunking

El chunking SHALL partir por secciones de segundo nivel, MUST dividir con overlap sólo secciones mayores al máximo sin romper listas numeradas ni tablas, y MUST derivar el `chunk_id` de documento, versión, localizador, contenido y versión de estrategia. La relevancia SHALL medirse sobre unidades de evidencia canónicas (`document@version#section`).

#### Scenario: Re-chunking
- **WHEN** el mismo documento se fragmenta dos veces
- **THEN** produce los mismos chunks e IDs

### Requirement: RF-03 Local deterministic embeddings with manifest

Los embeddings SHALL calcularse localmente y de forma determinística, sin descargas ni proveedores externos, con modelo, revisión, dimensión, tokenizer y normalización declarados en un manifest que indique explícitamente que no son semánticos. Cada chunk MUST guardar modelo, revisión y dimensión.

#### Scenario: Same text
- **WHEN** se embebe dos veces el mismo texto
- **THEN** el vector es idéntico y su norma L2 es 1

### Requirement: RF-04 Atomic publication and revocation

Publicar una versión SHALL insertar documento, chunks, `tsvector` y vectores en una única transacción con auditoría; un fallo MUST NOT dejar la versión visible ni afectar a la versión anterior. Una versión publicada MUST ser inmutable: republicar igual es no-op y con otro contenido es conflicto. Revocar MUST retirarla de todas las ramas de recuperación y de la resolución de citas.

#### Scenario: Embedding failure
- **WHEN** el proveedor de embeddings falla durante la publicación de la versión 2
- **THEN** no existe la versión 2 y la versión 1 sigue recuperable

#### Scenario: Revocation
- **WHEN** un curador revoca una versión
- **THEN** ninguna búsqueda la devuelve y su cita deja de resolverse

### Requirement: RF-05 Hard authorization and validity filters

Todas las ramas (lexical, códigos y vector) SHALL aplicar los mismos filtros duros: estado publicado, tenant global o propio, intersección de ACL con los roles del contexto autenticado, proveedor estructurado, vigencia y fecha de publicación respecto de `as_of`. Contenido fuera de ese universo MUST NOT devolverse ni usarse para completar el top-k, y su existencia MUST NOT revelarse.

#### Scenario: Other tenant
- **WHEN** un analista de `tenant-demo` busca contenido que sólo existe en `tenant-other`
- **THEN** no recibe resultados de ese documento en ningún modo

#### Scenario: Historical reconstruction
- **WHEN** se consulta con `as_of` anterior a la publicación de un incidente o a una nueva versión
- **THEN** sólo se recupera la versión vigente en esa fecha

### Requirement: RF-06 Hybrid retrieval with rank fusion

La recuperación híbrida SHALL combinar FTS por idioma, lookup exacto de códigos de error y búsqueda vectorial exacta por coseno, hasta 20 candidatos por rama, fusionados con RRF (`1 / (60 + rank)`) sin sumar scores crudos, devolviendo hasta 5 resultados con las ramas que los respaldan.

#### Scenario: Error code query
- **WHEN** se pregunta por el código E17 de prov-alfa
- **THEN** la sección vigente de E17 es el primer resultado

### Requirement: RF-07 Explicit abstention and resolvable citations

El sistema SHALL abstenerse con un motivo cuando ninguna evidencia autorizada coincide, cuando la consulta nombra un código no documentado o cuando la mejor evidencia cubre menos que el umbral de términos de la consulta. Cada resultado MUST exponer una cita `[document@version#chunk]` con localizador, hash y fecha efectiva, resoluble sólo dentro del universo autorizado.

#### Scenario: Unknown code
- **WHEN** se consulta por el código Z99
- **THEN** la respuesta es abstención sin citas

### Requirement: RF-08 Measured retrieval evaluation

Una evaluación reproducible SHALL comparar lexical, vector e híbrido con el mismo corpus, filtros y queries, reportando por split precision@5, recall@5, MRR, tasa de abstención correcta en queries sin respuesta (con intervalo de Wilson y n), abstenciones falsas, violaciones de ACL según un oráculo independiente y latencia p50/p95. El umbral de abstención MUST ajustarse sólo con `dev`, ninguna familia MUST aparecer en dos splits y el reporte MUST etiquetarse MEASURED con el alcance sintético.

#### Scenario: Report
- **WHEN** se ejecuta la evaluación en el stack local
- **THEN** produce un JSON con las métricas por modo y split, cero violaciones de ACL y sin familias filtradas entre splits

### Requirement: RF-09 Versioned schema and least privilege

El esquema de conocimiento SHALL crearse con la migración `0003_knowledge` sin drift respecto de las definiciones Core. El rol runtime MUST poder leer e insertar y sólo actualizar el estado de revisión, y MUST NOT poder borrar ni reescribir documentos o chunks.

#### Scenario: Rewrite attempt
- **WHEN** el rol runtime intenta modificar el contenido de un chunk
- **THEN** PostgreSQL lo rechaza por privilegios insuficientes
