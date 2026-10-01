## ADDED Requirements

### Requirement: RF-01 Independent review before human visibility

Cada borrador verificado SHALL revisarse con chequeos determinísticos (problemas de verificación, elementos requeridos del caso, hipótesis sin evidencia necesaria, contradicciones) y una revisión del modelo que MUST recibir sólo el snapshot del caso, los hechos, las afirmaciones y sus citas, sin razonamiento del planificador ni mensajes previos. El resultado SHALL ser el más conservador entre ambos y MUST declarar que no es una aprobación humana.

#### Scenario: Reviewer rejects
- **WHEN** el revisor devuelve `REJECTED`
- **THEN** la investigación termina `ABSTAINED` y el borrador no puede adoptarse

#### Scenario: Isolated input
- **WHEN** se invoca al revisor del modelo
- **THEN** su contexto no contiene pasos propuestos ni fragmentos no confiables

### Requirement: RF-02 Bounded reflection

Ante `NEEDS_MORE_EVIDENCE` con objeciones accionables, el orquestador SHALL permitir como máximo una nueva redacción y una nueva revisión, sólo si quedan al menos dos llamadas generativas; si no es posible o vuelve a fallar MUST escalar o abstenerse con motivo.

#### Scenario: Budget does not allow reflection
- **WHEN** el presupuesto por defecto ya usó planificación, redacción y revisión
- **THEN** no hay reflexión y la investigación se escala con el motivo registrado

### Requirement: RF-03 Human-owned recommendations

Sólo un analista SHALL proponer una recomendación (acción no operativa de un conjunto cerrado, motivo y versión esperada). Adoptar un borrador de investigación MUST exigir que pertenezca al mismo caso, esté `DRAFTED` y tenga revisión `SUPPORTED`. Una nueva recomendación MUST reemplazar a las pendientes anteriores e incrementar la versión del caso.

#### Scenario: Unreviewed draft
- **WHEN** un analista intenta adoptar un borrador sin revisión `SUPPORTED` o de otro caso
- **THEN** la propuesta se rechaza

### Requirement: RF-04 Segregation of duties

Una decisión SHALL requerir rol supervisor y MUST rechazarse si quien decide es el proponente o quien solicitó la investigación adoptada, aunque tenga ambos roles. Todo intento rechazado MUST auditarse.

#### Scenario: Self-approval (HU01)
- **WHEN** el proponente con rol supervisor intenta aprobar su propia recomendación
- **THEN** recibe 403, el caso no cambia y queda una entrada `decision.denied`

### Requirement: RF-05 Versioned, idempotent and serialized decisions

Una decisión SHALL incluir la versión esperada del caso, un motivo y una clave de idempotencia. MUST rechazarse con conflicto si la versión no es la vigente, el caso no está en revisión humana, la recomendación no está pendiente, expiró o el run del caso ya no es el más reciente del lote. Repetir la misma clave con el mismo contenido MUST devolver la decisión original; con otro contenido MUST ser conflicto. Decisiones concurrentes MUST producir exactamente una transición.

#### Scenario: Concurrent approvals (HU02)
- **WHEN** cuatro supervisores deciden a la vez sobre la misma versión
- **THEN** sólo una decisión se registra y las demás reciben conflicto

#### Scenario: Late evidence (RC10)
- **WHEN** se ejecuta un run más nuevo del lote antes de decidir
- **THEN** la recomendación queda `OBSOLETE` y la decisión responde 409

### Requirement: RF-06 Atomic effects without money movement

Registrar una decisión SHALL guardar decisión, estado de la recomendación, estado y versión del caso, auditoría y evento `ApprovalRecorded` en una transacción. La respuesta y el evento MUST declarar que no se ejecuta ningún movimiento de dinero. Cerrar un caso MUST requerir un supervisor, un motivo y la versión vigente.

#### Scenario: Approval effect
- **WHEN** un supervisor aprueba
- **THEN** el caso pasa a `APPROVED` con nueva versión y `operational_effect` indica que sólo se registró la decisión

### Requirement: RF-07 Reconstructible audit trail

Un auditor o supervisor SHALL poder reconstruir un caso: snapshot y reglas del run, recomendaciones, decisiones, investigaciones adoptadas con sus pasos MCP, citas y revisión, y la auditoría de todos esos recursos. La lectura MUST auditarse y un analista MUST NOT acceder a ella.

#### Scenario: Auditor reconstruction (UC08)
- **WHEN** un auditor pide la traza de un caso decidido
- **THEN** obtiene apertura, recomendación, intentos denegados, decisión e investigación con su evidencia

### Requirement: RF-08 Least privilege for decisions

El rol runtime SHALL poder insertar casos, recomendaciones y decisiones y actualizar sólo columnas de estado y versión; MUST NOT poder modificar ni borrar decisiones ni reescribir recomendaciones o la autoría de un caso.

#### Scenario: Rewrite attempt
- **WHEN** el rol runtime intenta actualizar una decisión
- **THEN** PostgreSQL lo rechaza por privilegios insuficientes
