## 1. Corpus e indexado

- [x] 1.1 Corpus `knowledge-v1` validado con manifest y queries etiquetadas; verificar T01 (AC01).
- [x] 1.2 Chunking `chunking/v1` y embeddings `hashing-ngram/v1` con manifest; verificar T02 (AC02).

## 2. Almacenamiento

- [x] 2.1 Migración `0003_knowledge`, tipo `Vector`, privilegios y job `knowledge-ingest`; verificar T04/T08 (AC03, AC08).

## 3. Retrieval

- [x] 3.1 Filtros duros comunes, ramas FTS/códigos/vector y RRF; verificar T03/T05/T06 (AC04, AC05).
- [x] 3.2 Abstención, advertencias de contenido no confiable y citas resolubles; verificar T03/T06 (AC06).

## 4. Evaluación y cierre

- [x] 4.1 Evaluación lexical/vector/híbrida con ajuste sólo en dev; verificar T07 (AC07).
- [x] 4.2 Gate completo, evidencia y archivo; verificar T09 (AC09).
