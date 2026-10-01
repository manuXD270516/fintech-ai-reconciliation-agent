# Criterios de aceptación — hybrid-knowledge-retrieval

Un criterio sólo pasa a **PASS** con evidencia enlazada. IDs RF: [requirements](specs/hybrid-knowledge-retrieval/spec.md); IDs T: [test strategy](test-strategy.md); IDs numéricos: [tasks](tasks.md). Detalle: [evidencia](evidence/README.md).

| ID | Criterio observable | Requirements | Tests | Tasks | Estado | Evidencia |
|---|---|---|---|---|---|---|
| AC01 | Corpus sintético versionado con manifest; metadatos inválidos, tarjetas y claves rechazados; instrucciones marcadas | RF-01 | T01, T02 | 1.1 | PASS | [T01](evidence/README.md#t01), [T02](evidence/README.md#t02) |
| AC02 | Chunks determinísticos por sección con unidades canónicas; embeddings locales determinísticos con manifest no semántico | RF-02, RF-03 | T02, T06 | 1.2 | PASS | [T02](evidence/README.md#t02), [T06](evidence/README.md#t06) |
| AC03 | Publicación atómica e inmutable; fallo de embeddings sin versión parcial; revocación retira en todas las ramas y citas | RF-04 | T04 | 2.1 | PASS | [T04](evidence/README.md#t04) |
| AC04 | Filtros duros idénticos en todas las ramas: tenant, ACL, publicado, vigencia y `as_of` (RG02, RG04) | RF-05 | T03, T05 | 3.1 | PASS | [T03](evidence/README.md#t03), [T05](evidence/README.md#t05) |
| AC05 | Híbrido FTS + códigos + vector con RRF k=60; RG01 con la versión vigente primero | RF-06 | T03, T06 | 3.1 | PASS | [T03](evidence/README.md#t03), [T06](evidence/README.md#t06) |
| AC06 | Abstención explícita (RG03) y citas resolubles sólo dentro del universo autorizado; contenido con instrucciones devuelto con advertencia | RF-07 | T03, T05, T06 | 3.2 | PASS | [T03](evidence/README.md#t03), [T05](evidence/README.md#t05), [T06](evidence/README.md#t06) |
| AC07 | Evaluación MEASURED lexical/vector/híbrido por split, ajuste sólo en dev, cero violaciones de ACL y sin fuga de familias | RF-08 | T07 | 4.1 | PASS | [T07](evidence/README.md#t07), [reporte](evidence/retrieval-eval.json) |
| AC08 | Migración `0003` sin drift e idempotente; rol runtime sin borrar ni reescribir conocimiento | RF-09 | T04, T08 | 2.1 | PASS | [T04](evidence/README.md#t04), [T08](evidence/README.md#t08) |
| AC09 | Gate completo verde y trazabilidad consistente para archivar | RF-08, RF-09 | T09 | 4.2 | PASS | [T09](evidence/README.md#t09), [gate](evidence/gate-all.log) |

Definition of Done de M3: AC01–AC09 en PASS con evidencia. Los objetivos numéricos EXPECTED de docs/07 no son criterio de aceptación: se reportan las métricas medidas y sus límites. El CI remoto sigue cubierto por AC06 de M0 (PENDING por facturación de GitHub).
