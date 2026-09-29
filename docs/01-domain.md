# Dominio, bounded contexts, actores y casos de uso

## Dominio

La conciliación compara observaciones de un mismo movimiento económico en sistemas diferentes. Un registro de pago, un intento, un evento de autorización, una captura y una liquidación no son automáticamente la misma entidad. El ledger interno tampoco es una fuente universal de verdad: cada atributo tiene procedencia y autoridad definida por una política versionada.

Hipótesis de alcance: dos proveedores ficticios, varias cuentas de comercio, USD y BOB como ejemplos, sin FX; comparación por cuenta, moneda, operación y referencias; imports CSV, APIs y eventos sintéticos. M2 resuelve relaciones 1:1. Capturas parciales, split settlement, fees, netting y relaciones 1:N/N:1 se reconocen como casos fuera de alcance y se derivan a investigación, nunca se fuerzan como matches.

### Lenguaje ubicuo y modelo conceptual

| Concepto | Identidad, contenido y relaciones |
|---|---|
| Payment | Intención económica; agrupa intentos, no equivale a una observación |
| PaymentAttempt | Intento en un proveedor/cuenta; distingue reintento técnico de nuevo cobro |
| TransactionObservation | Registro inmutable de una fuente: tenant, source, source_record_id, revision, provider, merchant_account, operation_type, payment/attempt refs, amount_minor, currency, status, occurred_at, received_at, effective_at, raw_hash, normalization_version |
| Money | Entero en unidad menor y moneda con exponente explícito; nunca float; conversión decimal exacta con rechazo de precisión excesiva |
| SourceArtifact | Archivo/payload original, hash, versión de parser, procedencia y estado de validación |
| ReconciliationBatch | Ventana [inicio, fin), timezone de negocio, source pair, cuenta, currency, source completeness, cutoff y watermark |
| ReconciliationRun | Snapshot de observaciones, batch revision, ruleset_version y resultado reproducible; un rerun crea nueva versión |
| MatchGroup | Relación propuesta o exacta entre observaciones; cardinalidad y regla que la justifica |
| Discrepancy | Una o varias diferencias tipadas; incluye monto, estado, fuente faltante, duplicado o processing error |
| InvestigationCase | Expediente versionado: discrepancias, asignación, evidencia, recomendación y estado de revisión |
| EvidenceItem | Afirmación, tipo epistemológico, referencias verificables, fecha efectiva y fecha de recuperación |
| Recommendation | Acción sugerida, alcance, versión del caso, evidencia, alternativas y restricciones |
| ApprovalDecision | Actor humano, rol, decisión, motivo, versión aprobada, expiración y timestamp |
| AuditEntry | Actor, acción, recurso, versión, correlación, resultado y referencias de evidencia |

El dinero se compara en la misma base: gross contra gross o net contra net sólo con un contrato explícito. El signo representa una dirección documentada por operación; un refund no se infiere sólo de un importe negativo. Autorización, captura, refund y chargeback conservan su vínculo y sus estados propios. El timestamp de llegada no reemplaza al de ocurrencia; se retienen offset original y UTC.

### Invariantes

1. Ninguna comparación cruza tenant, cuenta, moneda ni tipo de operación incompatible. Todos los identificadores externos están acotados por proveedor y cuenta.
2. Un replay idéntico no crea otra observación ni otro efecto. Mismo ID y misma revisión con distinto hash produce conflicto, no sobrescritura. Una actualización legítima tiene nueva revisión y conserva historia.
3. Una observación sólo pertenece a un match aceptado dentro del mismo run/source pair. Un match con A no implica transitivamente un match con B de otra fuente.
4. Exact match exige referencia fuerte compartida, candidato único, dinero idéntico y estados compatibles según política versionada. Monto y hora por sí solos nunca justifican match exacto.
5. No se declara transacción faltante definitiva antes del cierre y de confirmar completitud de fuentes. Timeout no equivale a ausencia. Datos tardíos reabren/versionan el resultado.
6. Las reglas generan hechos auditables. La IA no modifica observaciones, thresholds, reglas ni resoluciones.
7. Auditoría y cambios del negocio se confirman en la misma transacción cuando comparten almacenamiento. Se publica mediante outbox después del commit.
8. Aprobar una recomendación no ejecuta un movimiento monetario. Cerrar manualmente, aceptar un probable match o solicitar un ajuste son decisiones humanas trazables.

### Taxonomía del resultado

Separar `match_status` (`EXACT`, `PROBABLE`, `UNMATCHED`, `NOT_EVALUATED`) de `discrepancy_types[]` y `processing_status`. Un par puede tener a la vez amount mismatch y status mismatch; no se pierde una señal por elegir una categoría única. `WAITING_SOURCE` expresa incertidumbre de completitud; `MISSING_INTERNAL`/`MISSING_EXTERNAL` requieren ventana cerrada. `DUPLICATE_CANDIDATE` representa duplicación económica sospechada; deduplicación de transporte es otra cosa. `PROCESSING_ERROR` conserva la causa y puede impedir evaluar un match.

### Pipeline determinístico propuesto

Validación → deduplicación técnica → normalización → snapshot y completitud → candidatos por referencias fuertes → comparación de dinero/estado → exact matches únicos → discrepancias enlazadas → ranking de candidatos débiles → faltantes según watermark → expediente si hace falta.

Ordenar establemente por identidad para reproducibilidad; un empate se conserva como ambigüedad. La fase débil usa reglas explicables (referencias parciales, ventana temporal, cuenta, importe) y produce scores de ranking, no probabilidades calibradas. Tolerancia monetaria inicial: cero. Una excepción futura para fees o redondeo requiere nueva política, spec y pruebas; no se oculta con un epsilon genérico. Agrupar candidatos mediante índices/hash por claves; evitar comparar todos contra todos.

## Bounded contexts

| Contexto | Propietario de datos | Contrato con otros contextos |
|---|---|---|
| Ingestion & Normalization | Artefactos, receipts, observaciones, mapeos | Publica `ObservationNormalized` o `IngestionRejected`; adapta contratos externos |
| Reconciliation | Batches, snapshots, reglas, matches, discrepancias | Consume observaciones; publica `ReconciliationCompleted` y `DiscrepancyDetected` |
| Knowledge | Documentos, versiones, chunks, embeddings, índice | Sirve evidencia acotada por ACL y vigencia; no determina estados de pagos |
| Investigation | Plan, pasos, evidencia, borradores y revisión | Consume discrepancias; consulta contextos vía fachadas read-only/MCP |
| Case Management & Approval | Asignación, versiones, recomendaciones, decisiones | Publica `RecommendationReady`, `ApprovalRecorded`, `CaseClosed` |
| Audit & Access | Identidades, permisos, historial de acciones | Intercepta comandos/consultas sensibles y permite reconstruir decisiones |
| Evaluation | Datasets, oráculos, configuraciones y resultados | Ejecuta contra interfaces públicas; no escribe tablas operativas |

Son módulos con propiedad clara, no siete microservicios. Un PostgreSQL físico al inicio, con esquemas/roles y repositorios por contexto. No se permiten writes cruzados a tablas de otro módulo. Ingestion actúa como anti-corruption layer; los demás dependen del modelo normalizado. Investigación depende de conciliación y knowledge, nunca al revés. Eventual consistency entre workers; consistencia transaccional dentro de cada comando.

## Actores

| Actor | Acciones autorizadas | Restricciones |
|---|---|---|
| Analista de operaciones | Revisar discrepancias, investigar, aportar evidencia, proponer resolución | No aprobar su propia propuesta operativa |
| Aprobador/supervisor | Aprobar/rechazar/requerir investigación; aceptar match probable | Motivo obligatorio, versión vigente, segregación de funciones |
| Auditor | Consultar/exportar historial autorizado | Read-only; datos filtrados por tenant |
| Integración externa | Entregar archivos/eventos y consultar recepción propia | Scope por proveedor/cuenta; sin acceso a otros tenants |
| Administrador de plataforma | Gestionar configuración técnica y accesos | No gana aprobación operativa por ser administrador |
| Curador de knowledge | Validar/publicar versiones de documentos | No convierte incidentes similares en hechos del caso actual |
| Worker/agente | Normalizar, conciliar, investigar según identidad de servicio | Mínimo privilegio; agente sin permisos de resolución |
| Maintainer/evaluador | Mantener specs, fixtures y reportes | Datos sintéticos; no presentar simulaciones como desempeño real |

## Casos de uso

| ID | Trigger y flujo principal | Resultado y variantes |
|---|---|---|
| UC01 | Integración carga batch con idempotency key; validar filas y registrar hash | Receipt con válidos/rechazados; import parcial no marca fuente completa |
| UC02 | Worker normaliza moneda, importe, refs, operación y estado | Observación trazable; precisión inválida o mapping desconocido van a cuarentena |
| UC03 | Batch alcanza cutoff; worker crea snapshot y ejecuta reglas | Matches y discrepancias reproducibles; faltantes esperan completitud |
| UC04 | Llega replay, revisión o evento fuera de orden | Dedupe o nueva revisión; rerun versionado, sin borrar evidencia anterior |
| UC05 | Analista abre discrepancy case | Evidencia factual primero; probable match mantiene alternativas y score explicable |
| UC06 | Caso ambiguo requiere contexto | Planner limitado → MCP → retrieval → evidence → reviewer; abstención si faltan fuentes |
| UC07 | Supervisor revisa recomendación vigente | Aprueba/rechaza con motivo; conflicto de versión impide decisión obsoleta |
| UC08 | Auditor reconstruye el caso | Obtiene input snapshot, reglas, consultas, fuentes y decisión humana; acceso denegado queda auditado |
| UC09 | Curador ingiere runbook/incidente sintético | Nueva versión recuperable con citas; revocación elimina acceso desde búsquedas y cachés |
| UC10 | Evaluador ejecuta suite versionada | Reporte con evidencia MEASURED/SIMULATED y comparación contra EXPECTED |

Ejemplo sintético: captura interna `pay-042`, USD 10000, frente a captura del proveedor USD 9900 con la misma referencia. La diferencia de 100 unidades menores es un hecho; “fee descontado” es hipótesis hasta hallar evidencia aplicable. Un incidente parecido sólo respalda plausibilidad. El sistema no rebaja la discrepancia automáticamente ni aplica un ajuste.
