# Responsabilidades agénticas y aprobación humana

## Routing antes de invocar IA

El motor determinístico cierra su evaluación sin invocar LLM. Exact matches, dedupe de transporte, validaciones y diferencias numéricas se explican con plantillas y rule IDs. Una discrepancia evidente puede abrir directamente revisión humana; no necesita agentes sólo por ser una excepción.

Investigation se habilita por una razón explícita: candidatos ambiguos, documentación contextual necesaria, estado desconocido o contradicción entre fuentes. Un límite por caso impide investigaciones repetidas sin nueva evidencia. El operador puede pedir investigación, pero eso no amplía permisos ni presupuesto.

## Planner → Executor → Reviewer

La orquestación es una máquina de estados persistida y acotada, no un grupo autónomo de agentes conversando. Roles lógicos dentro de un worker; Evidence no necesita un modelo separado. El planner inicial usa una plantilla por tipo de discrepancy; el LLM sólo propone pasos adicionales del catálogo permitido.

| Rol | Entrada y responsabilidad | Salida y límite |
|---|---|---|
| Investigation Agent / Planner | Snapshot del caso, preguntas pendientes y tools autorizados; decidir qué evidencia falta | Plan de hasta 6 llamadas MCP; sin writes ni exploración libre de URLs |
| Investigation Agent / Executor | Ejecutar pasos aprobados por política; ReAct acotado de acción → observación → siguiente paso | Evidence bundle, conclusión provisional, alternativas y datos faltantes; nunca resolución |
| Evidence Agent | Validar procedencia, IDs, versión, timestamps y soporte de afirmaciones; separar categorías | Claims tipados; reglas determinísticas primero, modelo opcional sólo para soporte semántico |
| Reviewer Agent | Evaluar independientemente conclusión, evidencia original, alternativas y omisiones | `SUPPORTED`, `NEEDS_MORE_EVIDENCE` o `REJECTED`, con objeciones citadas; no aprobación humana |
| Orchestrator | Autorizar tools, limitar tiempos/tokens, persistir checkpoints, validar schemas | Recomendación revisada o escalamiento manual; no delega política al LLM |
| Humano | Inspeccionar evidencia y decidir con rol y versión vigentes | Aprobación/rechazo/reinvestigación auditable |

Evidence se implementa primero como fase verificadora determinística, preservando el rol solicitado sin agregar un “agente” innecesario. Reviewer usa una invocación aislada sólo para recomendaciones generadas por LLM; no recibe razonamiento privado ni historial irrelevante, sí recibe snapshots y evidencia. Un segundo modelo no garantiza independencia: medir errores correlacionados y comparar contra revisión con reglas y adjudicación humana.

### Contrato epistemológico

Cada claim incluye `claim_id`, `kind`, `statement`, `evidence_refs[]`, `limitations` y `as_of`.

- **FACT**: observación verificable en registro o documento versionado. “El documento indica X” no prueba que X haya ocurrido en este pago.
- **INFERENCE**: conclusión derivada de hechos, explicando qué regla o relación la respalda y qué alternativas siguen abiertas.
- **HYPOTHESIS**: explicación pendiente; incluye evidencia necesaria para confirmarla o refutarla.

Cada referencia permite resolver `source_id`, `version`, `record/chunk_id`, hash y localizador. Una cita existente pero irrelevante falla soporte semántico. Fuente inaccesible, caducada o contradictoria se muestra como limitación. Nunca elevar una hipótesis por repetición entre agentes.

Salida estructurada de investigación: `case_id`, `case_version`, `run_id`, `input_snapshot_hash`, `facts[]`, `inferences[]`, `hypotheses[]`, `contradictions[]`, `missing_evidence[]`, `recommended_next_step`, `confidence_assessment`, `citations[]`, `review_result`, `budget_usage`. Guardar resumen de justificación y decisiones de tools; no registrar cadenas privadas de pensamiento.

## ReAct, Reflection y límites

ReAct sirve para adaptar la siguiente consulta a una observación concreta. No se usa para aritmética, matching exacto ni lectura masiva de registros. Reflection sólo tras una objeción accionable del reviewer: una revisión adicional como máximo, con evidencia nueva o corrección concreta; nunca un loop para aumentar “confianza”. Si vuelve a fallar, abstenerse y escalar.

Presupuesto inicial **EXPECTED** por investigación completa: hasta 6 llamadas MCP, 4 llamadas generativas (investigation + reviewer y como máximo una pareja de revisión), 16 000 tokens de entrada/salida agregados y 60 s de wall time. El contexto individual se recorta reservando espacio para respuesta y revisión; las llamadas se cancelan al agotar presupuesto. Retries cuentan contra los límites. Embeddings se contabilizan por separado. Son políticas propuestas, pendientes de validación en M5/M7.

### Confianza y abstención

No usar autoconfianza del LLM como probabilidad. Antes de calibración, publicar `uncalibrated`, cobertura de evidencia y flags de contradicción; toda recomendación pasa revisión humana. La ausencia de evidencia necesaria, una contradicción material o un fallo de citas fuerza abstención cualquiera sea el score.

Después de calibrar en dev y verificar en holdout: umbrales iniciales **EXPECTED**, `p >= 0.90` permite recomendación revisada para humano; `0.65 <= p < 0.90` permite sólo solicitud de información/investigación adicional; `p < 0.65` abstiene. Revalidar por clase de discrepancia y proveedor. Un threshold jamás habilita ejecución operativa. El score de ranking de matches y los scores de retrieval no son `p`.

## Human-in-the-loop

Estados previstos: `OPEN → INVESTIGATING → REVIEW_PENDING → HUMAN_REVIEW → APPROVED | REJECTED | NEEDS_INFORMATION`. Sin IA: `OPEN → HUMAN_REVIEW` con recomendación manual o diagnóstico determinístico. `APPROVED` significa decisión registrada; no “pago ejecutado”. `CLOSED` necesita comando humano y motivo; rechazo puede cerrar o devolver el caso según decisión explícita. Nueva evidencia significativa vuelve obsoleta la recomendación, invalida aprobación pendiente y genera nueva versión.

Antes de aprobar, API verifica rol, tenant, separación proponente/aprobador, versión de caso y evidencia, expiración e idempotency key. Dos aprobaciones concurrentes: sólo una transición válida, la otra recibe conflicto o resultado idempotente. La transacción incluye decision, estado, audit y outbox. Frontend muestra diff de monto/estado, fuentes, hechos/inferencias/hipótesis, alternativas, objeciones, confianza no calibrada si aplica y efecto exacto de aprobar. Ningún botón de “aprobar todo” en el MVP.

M5 entrega sólo borradores para investigación; M6 habilita recomendaciones revisadas y decisión humana por API. Ejecución financiera externa queda fuera incluso de M10. Un futuro ejecutor requeriría nueva spec, autorización de alcance, idempotencia de proveedor, expiración de approval y reconciliación posterior.
