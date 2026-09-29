# Riesgos, seguridad y observabilidad

Evaluación cualitativa inicial; probabilidad no medida. Responsables son roles propuestos, no personas ya asignadas.

| Riesgo | Probabilidad / impacto | Mitigación y evidencia de aceptación | Dueño / gate |
|---|---|---|---|
| Falso match mueve interpretación económica | Media / crítico | Claves fuertes, unicidad, moneda/operación/base; negativos difíciles, cero falsos exactos observados | Domain owner / M2 |
| Duplicación por retries o carreras | Alta / alto | Unique constraints, inbox/outbox, decisiones con versión; fault injection entre commit/publish/ack | Backend owner / M2 |
| Evento tardío confundido con ausencia | Alta / alto | Watermarks, completitud, ventana explícita y reruns; casos de fuente parcial y out-of-order | Domain owner / M2 |
| Gross/net, fees, FX, timezone mal interpretados | Alta / alto | Contratos por proveedor, out-of-scope explícito, dinero exacto y fechas duales | Domain owner / M1–M2 |
| Fuentes/documentos obsoletos o contradictorios | Alta / alto | Vigencia/versiones y snapshots; citas al contenido usado, abstención | Knowledge owner / M3 |
| Alucinación o consenso falso entre agentes | Media / crítico | Claims tipados, soporte de citas, reviewer y humano; rubric con errores críticos | AI owner / M5–M7 |
| Prompt injection en docs/errores de proveedor | Alta / crítico | Contenido no confiable, catálogo cerrado, sin URLs libres ni write tools; ataques adversariales | Security owner / M4–M6 |
| Exfiltración/cross-tenant por tools o retrieval | Media / crítico | Autorización por recurso, RLS/roles, límites y cachés con tenant; tests de deny | Security owner / cada milestone |
| Aprobación obsoleta, suplantación o autoaprobación | Media / crítico | Identidad humana, RBAC, versión, expiración y separación de funciones | Backend owner / M6 |
| Fatiga de revisión humana | Media / alto | Resumen factual, evidencia visible, sin aprobación masiva; medir tasa de overrides y backlog | Operations owner / M8 |
| Costos/latencia por loops y reintentos | Alta / medio | Budgets, deadlines, cache de pasos, rate limits y circuit breakers | AI owner / M5 |
| Auditoría alterada o perdida | Media / alto | Append-only por permisos, atomicidad con comandos, export y restore checks | Platform owner / M6–M9 |
| Leakage de datos de test o overfitting sintético | Alta / alto | Split por familias, gold separado, holdout y límites públicos explícitos | Eval owner / M7 |
| Demo pública filtra secretos o expone servicios | Media / crítico | Synthetic-only, secret scan, auth, loopback local, puertos privados y least privilege | Maintainer / M0 y M10 |
| Dependencias vulnerables/cambios de SDK | Media / alto | Lockfiles, imágenes fijadas, escaneo, actualización bajo tests de contratos | Maintainer / M0–M9 |
| DB única y caída de broker | Media / alto | Backups/restore, outbox, cola acotada, alertas de disco; sin afirmar HA | Platform owner / M9 |
| Sobrearquitectura consume el proyecto | Alta / medio | Módulos antes que servicios, agentes sólo ante ambigüedad, gates pequeños | Architecture owner / todos |

## Threat boundaries y datos

Fronteras: navegador→API, fuentes→ingestion, worker→MCP, MCP→DB, documentos→prompt, servicio→proveedor de modelos y operador→aprobación. Autenticar/autorizar cada frontera relevante; identidad del agente no hereda permisos de aprobación de quien inició la investigación. El acceso de auditor no equivale a administrador DB.

No guardar ni mostrar PAN, CVV, nombres reales o secretos en fixtures. Payloads sintéticos se validan igual que fuentes no confiables. Logs redactan campos sensibles y no incluyen tokens, prompts completos ni filas financieras indiscriminadamente. En demo pública, rate limit, restricciones de upload/tamaño, CORS/origin control, protección CSRF si se usan cookies y TLS. Endpoints internos no se publican.

El rol de auditoría permite append, no update/delete. Esto mejora integridad frente a errores de aplicación, pero no hace el historial inmutable frente al administrador de PostgreSQL. Hash chain/export externo puede detectar alteración; almacenamiento con garantías de retención queda para requisitos futuros. Retención operativa propuesta para demo: inputs/trazas 30 días y eliminación reproducible; artefactos sintéticos de eval se conservan versionados. Antes de usar datos reales se necesitaría definir retención y obligaciones aplicables con los responsables correspondientes; no se afirma cumplimiento PCI u otro marco.

## Observabilidad

Trazas: `ingest → normalize → reconcile → investigate → MCP/retrieve → evidence → review → human decision`. Propagar correlation/causation/trace ID por HTTP, eventos y tools. Registrar versiones de reglas, documentos, prompts/modelos y hashes de snapshots. El audit trail responde “quién decidió qué y con qué evidencia”; telemetry responde “cómo se comportó el sistema”. No son intercambiables.

Métricas propuestas: ingest accepted/rejected, lag de outbox/consumidor, edad del batch incompleto, match/discrepancy por tipo, dead letters, retry count, tool latency/error, retrieval no-answer, invalid citations, abstention, reviewer disagreement, human queue age, approval conflicts, tokens/run y budget exhausted. No usar transaction_id o tenant_id sin límites como labels de métricas; IDs completos van en logs autorizados.

Alertas **EXPECTED** iniciales: outbox pendiente > 60 s, dead letters > 0, worker sin heartbeat > 60 s, backlog humano > 24 h y cualquier violación de permisos o cita inválida en recomendación lista para humano. Ajustar después de baseline; no son SLOs medidos. Runbooks: broker caído, DB llena, DLQ replay, embeddings indisponibles, evidencia retirada y rollback de ruleset.

## Recuperación y release

M9 demostrará restore de backup sintético y reanudación desde outbox sin duplicar efectos. RPO/RTO se medirán en ese ejercicio, no se prometen ahora. M10 requiere review de secrets/licencia/datos, aislamiento entre sesiones de demo, kill switch para IA y ruta determinística disponible. Operaciones de aprobación sólo cambian el expediente; ningún pago real se ejecuta.
