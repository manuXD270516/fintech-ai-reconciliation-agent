# bounded-investigation Specification

## Purpose
Investigar excepciones de conciliación de forma acotada y auditable: routing determinístico, evidencia obtenida sólo por el servidor MCP de lectura, verificación determinística de afirmaciones tipadas, presupuestos impuestos por código y borradores sin efecto operativo.

## Requirements

### Requirement: RF-01 Deterministic routing before any model call

El sistema SHALL decidir con reglas si un resultado necesita investigación y MUST NOT invocar modelos ni tools para matches exactos, resultados en espera de fuente o faltantes confirmados. Toda investigación MUST registrar un motivo explícito (candidatos ambiguos, contexto de diferencias, estado desconocido o posible duplicado).

#### Scenario: Exact match
- **WHEN** se solicita investigar un resultado EXACT
- **THEN** termina `NOT_NEEDED` con cero llamadas generativas y cero llamadas MCP

### Requirement: RF-02 Policy-bound planning

El plan SHALL partir de una plantilla por motivo. Los pasos propuestos por el modelo MUST rechazarse y registrarse si nombran una tool fuera del catálogo de lectura, usan argumentos de identidad o URLs, referencian transacciones ajenas al caso u otro proveedor, repiten un paso o exceden el presupuesto de tools.

#### Scenario: Injected write request
- **WHEN** el modelo propone `approve_resolution` o descargar una URL
- **THEN** los pasos se rechazan como `tool_not_in_read_catalog` y nunca se ejecutan

### Requirement: RF-03 Evidence only through the MCP boundary

La ejecución SHALL obtener evidencia exclusivamente mediante un cliente MCP contra `fintech-mcp-server`, lanzado como proceso separado con identidad y scopes fijados por el orquestador y sin credenciales de otros roles. Errores de tools MUST convertirse en brechas explícitas de evidencia.

#### Scenario: Tool timeout
- **WHEN** las tools exceden su timeout
- **THEN** la investigación registra las brechas y escala a una persona

### Requirement: RF-04 Deterministic evidence phase

Los hechos de registro (montos, estados, diferencia calculada, estado de plataforma) SHALL calcularse por código con referencias resolubles. Cada afirmación del modelo MUST tener tipo `FACT`, `INFERENCE` o `HYPOTHESIS` y citas resolubles; un `FACT` MUST citar al menos un registro (un documento no prueba un evento del pago) y sus cifras MUST aparecer en los registros citados. Las afirmaciones que fallan MUST descartarse y registrarse.

#### Scenario: Similar incident presented as fact
- **WHEN** el modelo afirma como FACT que un incidente causó la diferencia citando sólo el documento
- **THEN** la afirmación se descarta y la investigación se abstiene

#### Scenario: Faithful draft
- **WHEN** el modelo cita hechos de registro y presenta el incidente como hipótesis con la evidencia necesaria
- **THEN** el borrador conserva hechos, inferencias e hipótesis separados y citados

### Requirement: RF-05 Bounded execution and explicit termination

Cada investigación SHALL tener presupuesto de 6 llamadas MCP, 4 llamadas generativas, 16 000 tokens y 60 s, verificado antes de cada llamada. Agotar un límite, una salida malformada o un fallo de citas MUST terminar en `ABSTAINED` o `ESCALATED` con motivos, nunca en un borrador con afirmaciones no verificadas.

#### Scenario: Endless planning
- **WHEN** el modelo propone diez pasos adicionales
- **THEN** se ejecutan como máximo seis llamadas en total y el resto se rechaza por presupuesto

### Requirement: RF-06 Draft contract without operational effect

El resultado SHALL seguir el contrato de docs/04 (caso, versión, snapshot hash, hechos, inferencias, hipótesis, contradicciones, evidencia faltante, siguiente paso, evaluación de confianza `uncalibrated`, citas, uso de presupuesto) con `operational_effect: none`, etiqueta `SIMULATED` cuando el proveedor es el scripted y un siguiente paso de un conjunto cerrado no operativo.

#### Scenario: Model recommends approving
- **WHEN** el modelo devuelve `APPROVE_RESOLUTION` como siguiente paso
- **THEN** se reemplaza por `HUMAN_REVIEW`, se registra el problema y la investigación se abstiene

### Requirement: RF-07 Persisted state machine and idempotent requests

Cada transición SHALL persistirse. Una solicitud MUST ser idempotente por tenant, caso y hash del snapshot de entrada, y su creación MUST confirmarse junto con auditoría y el evento `InvestigationRequested`. Sólo un proceso MUST ejecutar una investigación a la vez (claim con lease) y un estado terminal MUST ser definitivo.

#### Scenario: Duplicate delivery
- **WHEN** el evento llega a dos consumidores
- **THEN** uno ejecuta y el otro informa duplicado; hay una sola auditoría de finalización

### Requirement: RF-08 Model providers behind one interface

Los proveedores SHALL implementar una interfaz común con uso de tokens reportado o estimado (marcado). El proveedor por defecto MUST ser el scripted local; el proveedor real MUST ser Ollama local por HTTP, alcanzable sólo por loopback o red interna, desactivado por defecto. Ningún proveedor de IA externo MUST configurarse.

#### Scenario: Unknown provider requested
- **WHEN** `RECON_MODEL_PROVIDER` pide un proveedor externo
- **THEN** la configuración se rechaza

### Requirement: RF-09 Authorized API access

Sólo un analista SHALL poder solicitar una investigación y analistas, supervisores y auditores MUST poder leerla dentro de su tenant; investigaciones de otro tenant MUST responder 404.

#### Scenario: Auditor requests an investigation
- **WHEN** un auditor intenta solicitar una investigación
- **THEN** recibe 403
