# Propuesta de arquitectura

Estado: decisiones propuestas para el MVP, sin software ni benchmarks. Objetivo: demostrar corrección, trazabilidad y recuperación ante fallas con complejidad operativa acotada.

## ADR-001 — Backend FastAPI

| Criterio del proyecto | NestJS | FastAPI |
|---|---|---|
| API y organización | Módulos, DI y convenciones consistentes; encaja bien en equipos TypeScript | Tipos Python, validación y OpenAPI; exige imponer límites entre módulos |
| Eventos | Abstracciones de transporte integradas | Cliente explícito del bus y workers; más decisiones propias |
| IA, retrieval y evals | Viable, pero algunas herramientas requerirían integrar Python | Un lenguaje para dominio, embeddings, investigación y evals |
| Frontend React | Comparte lenguaje, no elimina necesidad de validar contratos | Cliente TypeScript generado desde OpenAPI; contrato versionado |
| CPU y durabilidad | Trabajo intensivo fuera del proceso HTTP | Trabajo intensivo fuera del proceso HTTP; async no acelera CPU |
| Costo de mantenimiento aquí | Excelente si el objetivo principal fuese una plataforma TypeScript | Menos runtimes de backend para un repositorio centrado también en AI systems |

**Decisión: FastAPI**, con dominio Python independiente del framework. Python tipado, validación de límites de entrada, PostgreSQL mediante una capa de persistencia explícita y migraciones versionadas. Elegir NestJS sería razonable con equipo predominantemente TypeScript o integraciones existentes; no hay evidencia para afirmar superioridad de throughput de uno en este proyecto. FastAPI documenta concurrencia async; NestJS documenta sus transportes de microservicios. [FastAPI](https://fastapi.tiangolo.com/async/), [NestJS](https://docs.nestjs.com/microservices/basics).

No introducir ambos backends en el MVP. No ejecutar trabajos durables en tareas en memoria del servidor HTTP.

## ADR-002 — Monolito modular y procesos especializados

API, worker de ingestion/reconciliation y worker de investigación comparten un núcleo de dominio y contratos, pero tienen procesos y permisos distintos. Knowledge ingestion es un job del worker al inicio. `fintech-mcp-server` es un proceso separado para ejercitar un límite MCP real. React consume la API; jamás accede directamente a DB ni al LLM.

Estructura futura, no creada en esta fase: `apps/api`, `apps/worker`, `apps/mcp-server`, `apps/web`, `packages/domain`, `packages/contracts`, `evals`, `tests`, `infra`. Adaptadores externos reemplazables; reglas puras sin imports de LLM, bus o HTTP. Partir en servicios por contexto sólo cuando haya necesidades medidas de ownership, despliegue o escalado.

## ADR-003 — PostgreSQL + pgvector

PostgreSQL conserva observaciones, snapshots, expedientes, outbox/inbox, auditoría y knowledge. Usar `bigint` con validación de rango para unidades menores y política versionada de exponentes; referencias scoped, claves únicas, foreign keys, control optimista de versiones y transacciones para invariantes. No guardar dinero como float.

Vectores y full-text search en el mismo motor reducen infraestructura. La documentación de pgvector permite combinar búsqueda vectorial con full-text y RRF; HNSW queda condicionado al tamaño/latencia medidos, con baseline exacto y evaluación del recall después de filtros. [pgvector](https://github.com/pgvector/pgvector).

Artefactos fuente sintéticos: volumen local en demo; futura interfaz para object storage, sin desplegar otro producto inicialmente. DB guarda URI autorizada y hash. Evidencia siempre referencia una versión inmutable; no depende de que una URL externa siga igual.

## ADR-004 — Event bus NATS JetStream

Elegir NATS JetStream para streams persistidos, consumidores durables y replay en una demo local. RabbitMQ también cubre trabajo asíncrono; Kafka añadiría complejidad no justificada por el alcance actual. JetStream soporta persistencia y diferentes garantías de entrega; este diseño asume **at-least-once** y no depende de “exactly once” extremo a extremo. [NATS JetStream](https://docs.nats.io/concepts/jetstream).

Sobre propuesto: `event_id`, `event_type`, `schema_version`, `aggregate_id`, `aggregate_version`, `tenant_id`, `occurred_at`, `correlation_id`, `causation_id`, `traceparent`, `payload_ref`. Payload pequeño, sin documentos ni datos sensibles completos. Ejemplos: `ObservationNormalized.v1`, `ReconciliationCompleted.v1`, `DiscrepancyDetected.v1`, `InvestigationRequested.v1`, `RecommendationReady.v1`, `ApprovalRecorded.v1`.

1. Comando persiste estado + audit entry + outbox en una transacción PostgreSQL.
2. Relay publica con event_id estable y registra confirmación del broker. Un crash entre publish y marca puede duplicar el mensaje.
3. Consumidor usa inbox con unique `(consumer, event_id)`; efecto local e inbox se confirman juntos antes del ack. Mensajes repetidos producen no-op.
4. No asumir orden global. aggregate_version detecta gaps y eventos viejos; lectura del snapshot permite recuperar estado. Particionar lógicamente por agregado cuando se requiera secuencia.
5. Retries exponenciales con jitter, máximo de intentos y timeout; agotamiento a stream de dead letters con razón y herramientas de replay auditadas. Replay conserva event_id; un nuevo comando legítimo usa identidad nueva y causation_id.
6. Jobs costosos usan checkpoints/leases y presupuesto por run. Llamadas LLM repetidas pueden generar costo tras un crash: caché por step/input hash y registro de intentos, sin prometer exactamente una invocación externa.

Eventos no equivalen a event sourcing: DB es el estado autorizado y se conserva historial necesario. Backpressure limita imports y concurrencia; el bus no transporta archivos completos.

## Interfaces y consistencia

API conceptual futura: recepción de artefactos, consulta de batches/runs/cases, solicitud de investigación y decisiones humanas. Comandos asíncronos devuelven receipt/job_id; las lecturas muestran estado y versión. Decisiones sobre un caso requieren `expected_version`, idempotency key y motivo; conflicto responde sin aplicar efectos.

Transacción crítica: verificar identidad/rol, segregación de funciones, versión y expiración; guardar decisión + transición + auditoría + outbox de forma atómica. Revocar permisos invalida sesiones y se vuelve a verificar en el comando, no sólo en el frontend.

## Disponibilidad y degradación

Caída del LLM, embeddings o MCP no impide conciliación determinística; genera investigación pendiente/manual. Bus caído acumula outbox con alerta; si se agota almacenamiento se rechaza nueva ingestión de forma explícita. DB no disponible: no aceptar writes como exitosos. Readiness distingue dependencia crítica de función opcional. Documento ausente o ambiguo produce abstención, nunca una respuesta inventada.

## ADR-005 — Observabilidad y seguridad desde el inicio

M0 incluye health checks, logs estructurados y request_id; M1–M6 propagan tenant autorizado, correlation y trace IDs sin exponer datos. M9 consolida OpenTelemetry, dashboards, alertas y pruebas de fallas; no pospone auth, auditoría ni idempotencia hasta el final. Modelo local single-user sólo bajo bind loopback; demo pública exige autenticación y aislamiento desde el despliegue.

Sin objetivo de HA o cumplimiento regulatorio certificado en el MVP. Los cambios que añadan movimientos de dinero, datos reales o ejecución externa requieren nuevos requisitos y otro threat model.
