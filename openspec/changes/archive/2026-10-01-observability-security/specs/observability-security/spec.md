## ADDED Requirements

### Requirement: RF-01 Optional end-to-end tracing

El sistema SHALL propagar el contexto W3C de traza desde la petición HTTP, a través del outbox y NATS, hasta el worker, el investigador y el servidor MCP cuando el exportador OTLP está configurado. Sin configuración, la telemetría MUST quedar apagada sin escribir contexto. Ningún span MUST llevar tenant, sujeto, montos ni cabeceras de autorización.

#### Scenario: Investigation trace
- **WHEN** con el perfil `observability` activo un analista pide una investigación
- **THEN** Jaeger contiene una sola traza con spans de `recon-api`, `recon-worker`, `recon-investigator` y `fintech-mcp-server`, sin atributos prohibidos

### Requirement: RF-02 Aggregated metrics

`GET /metrics` SHALL exponer métricas en formato Prometheus con etiquetas de baja cardinalidad: plantillas de ruta, clases de estado, valores de enumeraciones y nombres de tools. MUST NOT incluir identificadores de tenant, sujeto o recurso. Una fuente que no responde MUST reportarse como caída sin que falle el scrape.

#### Scenario: Unavailable source
- **WHEN** NATS no responde durante un scrape
- **THEN** `/metrics` responde 200 con `recon_metrics_source_up{source="messaging"} 0`

### Requirement: RF-03 Verified alerts

Las reglas de alerta SHALL evaluarse sobre `/metrics` con umbrales EXPECTED: outbox estancado, dead letters sin triar, latidos ausentes, backlog humano, rechazos de permisos de tools y fuentes caídas. Cada regla MUST enlazar un runbook existente y MUST verificarse disparando y limpiando.

#### Scenario: Broker outage
- **WHEN** NATS y el worker están detenidos con un run pedido
- **THEN** disparan `MetricsSourceDown`, `OutboxStalled` y `WorkerHeartbeatMissing`, y se limpian tras la recuperación

### Requirement: RF-04 Exact recovery and auditable dead-letter triage

Tras una caída del broker, los comandos aceptados SHALL completarse una sola vez. Los dead letters SHALL triarse con operador y motivo auditados. Un mensaje veneno MUST NOT re-publicarse, y re-publicar dos veces el mismo evento MUST NOT duplicar efectos.

#### Scenario: Duplicate replay
- **WHEN** dos copias del mismo evento agotado se re-publican desde el DLQ
- **THEN** existe un único artefacto y una única observación, y la auditoría registra cada acción

### Requirement: RF-05 Backup and restore check

El sistema SHALL ofrecer un backup del esquema `recon` y un chequeo de restore sobre una base temporal que compare conteos por tabla y un digest del audit trail con los registrados en el backup. El chequeo MUST reportar tiempo de restore y filas escritas después del backup, y MUST NOT modificar la base viva.

#### Scenario: Restore check
- **WHEN** se ejecuta `restore-check` con un dump recién creado
- **THEN** conteos y digest coinciden y la base temporal se elimina

### Requirement: RF-06 Runbooks

El repositorio SHALL incluir runbooks para broker caído, DLQ y replay, base de datos llena, backup y restore, investigador no disponible, evidencia retirada, rollback de ruleset y backlog humano. Cada uno MUST tener comandos reales e indicar qué fue ejercitado y qué no.

#### Scenario: Withdrawn evidence
- **WHEN** un operador ejecuta el comando de revocación del runbook
- **THEN** el documento deja de recuperarse en todas las ramas y la revocación queda auditada

### Requirement: RF-07 Secret scan and access review

El gate SHALL escanear toda la historia git en busca de formatos de credenciales, PAN con Luhn válido y rutas prohibidas, y MUST fallar ante cualquier hallazgo. Una matriz ruta × rol declarada MUST coincidir con lo que la API aplica. La revisión de seguridad MUST registrar hallazgos con severidad y estado.

#### Scenario: Undeclared route
- **WHEN** se agrega una ruta `/v1` que no está en la matriz
- **THEN** el test de la matriz falla
