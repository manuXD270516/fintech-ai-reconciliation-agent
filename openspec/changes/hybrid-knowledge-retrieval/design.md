## Context

Implementa [docs/06-rag.md](../../../docs/06-rag.md) con la decisión D04 de [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md): embeddings determinísticos locales y FTS + vector + RRF reales en pgvector. Los casos RG01–RG04 de [docs/07-evals.md](../../../docs/07-evals.md) son parte de la suite.

## Goals / Non-Goals

**Goals:** filtros duros idénticos en todas las ramas, versiones inmutables con publicación atómica, abstención explícita, citas resolubles y baselines medidos honestamente.

**Non-Goals:** calidad semántica, reranking, ANN, curaduría por UI.

## Decisions

- **Embeddings de hashing.** Se eligió hashing firmado de palabras y trigramas (256 dims) porque D04 prohíbe descargas y proveedores. Captura similitud superficial/morfológica, no semántica; el manifest lo declara (`semantic: false`) y los reportes lo repiten. Cambiar de modelo exige reindexado completo con `index_version` nueva.
- **FTS con OR.** `websearch_to_tsquery` exige todos los términos y falla con preguntas naturales. Se construye un `tsquery` disyuntivo a partir de los lexemas del propio `to_tsvector(config, query)` para español e inglés, y se rankea con `ts_rank_cd`; cada chunk usa la configuración de su idioma.
- **Lookup exacto de códigos.** Los códigos (`[A-Z]\d{2}`) se extraen al indexar a `error_codes[]` (GIN) porque la tokenización lingüística podría alterarlos. Sólo la rama híbrida los usa como rama propia; la regla de abstención por código no documentado se aplica igual a los tres modos para que la comparación sea justa.
- **RRF.** `score = Σ 1/(60 + rank)` por rama, desempate por `chunk_id`. No se suman scores crudos de ramas distintas.
- **Abstención.** Tres reglas, en orden: sin evidencia autorizada; código pedido ausente en los resultados; cobertura de términos de la consulta (sin stopwords, stemming mínimo de plurales) en la mejor evidencia menor al umbral. El umbral se ajusta en `dev` maximizando `(recall@5 + abstención correcta) / 2` (empate: el menor) y se fija en código (`ABSTAIN_COVERAGE = 0.6`); `holdout` sólo se reporta.
- **Filtros duros.** Un único fragmento SQL `_AUTHORIZED` se aplica en las tres ramas y en la resolución de citas, con parámetros enlazados. El tenant y los roles vienen del contexto autenticado; el proveedor, de un campo estructurado.
- **Publicación.** Lock advisory por `document_id`, comprobación de versión existente (igual → no-op, distinta → conflicto), inserción de documento y chunks con `to_tsvector(regconfig, título + contenido)` y vector, y auditoría en la misma transacción. Los embeddings se calculan dentro de la transacción para que un fallo deshaga todo.
- **`search_path`.** El rol runtime usa `recon, public`: `public` sólo aporta el tipo y operadores de pgvector y nadie tiene `CREATE` en él.
- **Oráculo de ACL independiente.** La evaluación recalcula la autorización con los metadatos del corpus en Python, no con el SQL bajo prueba.

## Risks / Trade-offs

- Con top-5 fijo y 1–2 unidades relevantes por query, precision@5 tiene un techo de 0.2–0.4; se reporta tal cual, sin recortar resultados para inflarla.
- El set de queries es pequeño (38): los intervalos de confianza son anchos y el umbral puede sobreajustar `dev`; `holdout` muestra la degradación.
- La regla de cobertura es léxica: preguntas sin respuesta que comparten vocabulario con el corpus pueden no abstenerse (casos documentados en la evidencia).
