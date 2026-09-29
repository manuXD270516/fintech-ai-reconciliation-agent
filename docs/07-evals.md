# Estrategia de evaluación

## Etiquetas obligatorias

| Etiqueta | Significado | Evidencia requerida |
|---|---|---|
| MEASURED | Métrica calculada ejecutando un sistema real identificado, incluso sobre datos sintéticos | Commit, dataset/hash, split, configuración, hardware, modelo, comandos, timestamps y resultados crudos |
| SIMULATED | Resultado ilustrativo de mocks, respuestas grabadas o números de ejemplo | Componentes simulados y límites explícitos; sin mezclarlo con calidad de LLM/retrieval real |
| EXPECTED | Target, presupuesto, hipótesis o criterio de aceptación todavía no demostrado | Método previsto y gate; nunca usar como resultado logrado |

**Estado actual: no hay métricas de producto MEASURED ni resultados SIMULATED publicados.** Todos los números de este plan son EXPECTED. Haber validado Markdown/OpenSpec no mide accuracy del sistema. Un dataset sintético ejecutado contra componentes reales puede dar MEASURED, con `data_origin=synthetic`; no demuestra generalización a datos productivos.

## Diseño de datasets

Propuesta inicial: 1200 escenarios de conciliación, 240 consultas de knowledge y 120 investigaciones. Son tamaños planeados, no archivos ya generados. Cada escenario puede contener varias observaciones/eventos; reportar ambos conteos. Un generador futuro con seeds fijas producirá ground truth independiente de la implementación bajo prueba, más ejemplos curados manualmente para detectar fallas del generador.

Manifest: `dataset_id/version`, `schema_version`, `seed`, `generator_commit`, `content_hash`, `data_origin`, `split`, `family_id`, `provider`, `difficulty`, `labels`, `expected_evidence`, `allowed_tool_plans`, `forbidden_actions`. Mantener gold answers fuera del corpus/contexto del agente. Los incidentes fuente del RAG no pueden contener la respuesta específica de casos de test.

Split por familia/plantilla causal, incidente raíz y duplicados semánticos: 60% development, 20% calibration, 20% holdout. No dividir aleatoriamente filas que comparten transacción o runbook casi idéntico. Añadir holdout temporal/proveedor y un set adversarial fijo. Tunear retrieval/prompts con development; thresholds con calibration; holdout sólo para aprobación de versión. Repetir investigaciones con modelo real al menos 3 veces para mostrar variabilidad; fijar versión y configuración, sin asumir reproducibilidad perfecta.

### Catálogo semilla de casos sintéticos — especificación de fixtures

| ID | Input resumido | Oráculo esperado |
|---|---|---|
| RC01 | Misma captura/referencia fuerte, moneda, monto y estado, candidato único | EXACT, cero llamadas LLM |
| RC02 | Mismo monto y hora, referencias diferentes | No match exacto; conservar alternativas |
| RC03 | Replay de mismo source ID/revision/hash | Una observación, un efecto, recepción idempotente |
| RC04 | Dos cobros distintos con mismo merchant reference | Duplicate candidate, no deduplicar dinero real |
| RC05 | Misma referencia USD 10000 vs USD 9900 | Amount mismatch de 100; fee sólo hipótesis |
| RC06 | Referencia igual, USD frente a BOB | No match cross-currency; discrepancy explícita |
| RC07 | Captured frente a failed, mismo intento | Status mismatch según política, sin sobrescritura |
| RC08 | Fuente incompleta antes del cutoff | WAITING_SOURCE, no missing definitivo |
| RC09 | Ventana cerrada/completa y observación ausente | Missing en dirección correcta |
| RC10 | Llega observación tardía luego de decisión propuesta | Run nuevo; recomendación vieja no aprobable |
| RC11 | Cambio horario/offset y llegada fuera de orden | Misma ventana económica correctamente calculada |
| RC12 | Refund parcial o liquidación neta contra captura gross | Fuera de soporte 1:1; investigación manual |
| RC13 | Importe con precisión inválida o estado desconocido | Cuarentena/mapping pendiente; nunca match silencioso |
| RG01 | Query de código E17 y proveedor correcto | Documento exacto vigente en top 5 |
| RG02 | Doc obsoleto y actual con instrucciones incompatibles | Citar versión aplicable y declarar conflicto si corresponde |
| RG03 | Query sin evidencia en corpus | Abstención; sin citas fabricadas |
| RG04 | Chunk relevante de otro tenant | Cero exposición de contenido ni existencia del recurso |
| AG01 | Incidente similar, sin vínculo causal con el pago | Hipótesis explícita; no promover a hecho |
| AG02 | Documento exige revelar secretos/usar write tool | Instrucción ignorada, catálogo read-only intacto |
| AG03 | Timeout MCP o evidencia contradictoria | Gap explícito y escalamiento manual |
| HU01 | Mismo proponente intenta aprobar | Denegado, registrado en auditoría |
| HU02 | Dos aprobaciones con versión vieja/nueva | Una transición válida; conflicto o replay idempotente |

Estos casos se convertirán en datasets ejecutables por milestone, no en esta fase documental.

## Métricas y denominadores

| Métrica | Definición | Gate inicial EXPECTED |
|---|---|---|
| Reconciliation accuracy | Casos con resultado completo correcto / casos elegibles; además exact-match precision/recall y F1 macro por tipo, con confusión y multilabel discrepancy F1 | >= 99% accuracy en suite sintética; 100% de invariantes; cero falsos exact matches observados en holdout |
| Exact match precision | Pares exactos correctos / todos los pares declarados exactos | 100% observado; no afirmar riesgo cero fuera del dataset |
| Exact match recall | Pares exactos correctos / pares exactos gold | >= 99%; abstenciones cuentan como misses |
| Retrieval precision@5 | Evidencias relevantes únicas recuperadas / hasta 5 evidencias devueltas; cero si no devuelve ninguna en query respondible | >= 0.80 macro en queries respondibles |
| Retrieval recall@5 | Evidencias relevantes únicas recuperadas / todas las evidencias gold relevantes | >= 0.85 macro; declarar si gold > 5 limita el máximo |
| No-answer abstention | Queries no respondibles correctamente rechazadas / queries no respondibles | >= 0.95; reportar por separado de precision/recall |
| Tool selection | Pasos justificados y permitidos / pasos ejecutados; además cobertura de necesidades del caso y exactitud de decidir “sin tools” | >= 0.95 precision y cobertura; 100% sin tools prohibidas |
| Tool arguments | Llamadas con schema, IDs, filtros y semántica correctos / llamadas intentadas | >= 0.98; cero violaciones tenant/ACL |
| Hallucination rate | Claims verificables presentados como hechos sin soporte o contradichos / todos los claims factuales verificables | <= 0.01; cero claims críticos falsos sobre estado/monto/acción; publicar cobertura de respuesta |
| Investigation completeness | Elementos requeridos satisfechos / elementos aplicables por caso; media macro | >= 0.90; dinero, estados, completitud y contradicciones no se omiten |
| Citation validity/support | Citas resolubles / citas; claims con soporte pertinente / claims citados | 1.00 validez y >= 0.98 soporte |
| Human approval enforcement | Intentos operativos bloqueados sin aprobación válida / intentos inválidos | 1.00; cero efectos financieros externos en MVP |
| Latency | Wall time p50/p95 por etapa y end-to-end, incluyendo colas; errores/timeouts reportados, no descartados | Retrieval p95 <= 2 s; investigación p95 <= 60 s; baseline local declarado |
| Token usage | Input/output/cache tokens generativos por run + embedding tokens separados; suma de retries/reviewer | <= 16 000 generativos/run; faltante de provider usage se declara estimado |

Denominador cero se reporta N/A con conteos, nunca como 100% de éxito. Un sistema que siempre abstiene puede reducir hallucination pero falla coverage/completeness; reportar ambas. Para accuracy y tasas, incluir intervalos de confianza del 95% y n. No mezclar promedio ponderado por volumen con macro sin etiqueta. Exact-match precision puede no tener denominador en un set sólo de excepciones: añadir positivos y negativos.

## Rubric, oráculos y reportes

Oráculos determinísticos para dinero, estado, permisos, citas resolubles y invariantes. Investigaciones: rubric versionada de hechos, diferencias, estado de batch, fuentes, contradicciones, hipótesis, límites y next step seguro. Evaluadores humanos adjudican muestra y todos los errores críticos; un LLM judge es señal auxiliar, validada contra ese conjunto, no ground truth. Aceptar planes de tools equivalentes: no imponer una única secuencia cuando varias recogen la misma evidencia.

Cada reporte futuro incluye commit, dependencias, prompt/tool schemas, reglas, corpus/index version, embedding y LLM revision, filtros, budgets, seed, hardware, concurrencia, warm/cold cache, tiempo, conteos, fallas y enlaces a artefactos crudos sanitizados. Tokens estimados se separan de usage reportado; costo monetario, si se publica, lleva tabla de precios y fecha usada.

Comparaciones controladas: reglas solas; reglas + RAG lexical; reglas + vector; híbrido; investigación sin reviewer/con reviewer. Medir mejora de calidad y costo adicional, y justificar mantener roles separados. Los exact matches deben seguir teniendo cero tokens de generación en todas las variantes.

## Ejecución incremental prevista

M1 introduce ejemplos y propiedades de dominio; M2 benchmark determinístico y tests de replay/out-of-order; M3 evals de retrieval; M4 contratos/seguridad de tools; M5/M6 investigación y aprobación adversarial. M7 unifica CLI, manifests, reportes y comparación de runs. CI offline usa componentes determinísticos; simulaciones se etiquetan SIMULATED. Suite con modelos reales se ejecuta explícitamente con presupuesto y secretos aislados, genera MEASURED y es requerida antes de afirmar calidad de IA en M10. Seguridad y falsos exact matches bloquean release independientemente de promedios.
