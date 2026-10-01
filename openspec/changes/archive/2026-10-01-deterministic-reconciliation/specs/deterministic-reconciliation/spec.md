## ADDED Requirements

### Requirement: RF-01 Idempotent artifact reception

El sistema SHALL recibir artefactos sintéticos por HTTP (CSV en `POST /v1/artifacts`) y por eventos JetStream, identificados por tenant, fuente, proveedor y clave de idempotencia. Reenviar la misma clave con el mismo contenido MUST devolver el recibo original sin nuevos efectos; reutilizar la clave con otro contenido MUST rechazarse como conflicto. El tenant MUST provenir de la identidad autenticada del canal (token o subject), nunca del contenido.

#### Scenario: Artifact replay
- **WHEN** una integración reenvía el mismo artefacto con la misma clave
- **THEN** recibe el recibo original marcado como `replayed` y no se crean observaciones, auditoría ni eventos nuevos

#### Scenario: Key reused with other content
- **WHEN** la misma clave llega con contenido distinto
- **THEN** la API responde 409 y nada se persiste

#### Scenario: Tenant spoofing in content
- **WHEN** una fila o evento declara un tenant distinto del autenticado
- **THEN** la fila queda en cuarentena con `scope_violation`

### Requirement: RF-02 Row validation and quarantine

La normalización SHALL validar cada fila con un parser versionado y MUST poner en cuarentena las filas con campos faltantes, valores inválidos, precisión excesiva, mappings desconocidos o alcance incorrecto, con un código identificable, sin adivinar valores y sin bloquear las filas válidas del mismo artefacto. Un encabezado inválido MUST rechazar el artefacto completo.

#### Scenario: Mixed artifact
- **WHEN** un artefacto contiene una fila con `10.005 USD` y otra válida
- **THEN** la válida se ingiere y la otra queda en cuarentena con `invalid_precision`

#### Scenario: Unknown provider status
- **WHEN** una fila trae un estado sin mapping
- **THEN** queda en cuarentena con `unknown_mapping` y su referencia produce `PROCESSING_ERROR` en la conciliación

### Requirement: RF-03 Batches with explicit source completeness

Un lote SHALL crearse por API con su alcance, ventana, zona horaria, par de fuentes y cutoff, y cada fuente MUST marcarse completa mediante un comando explícito y auditado. Una importación parcial MUST NOT marcar la fuente como completa.

#### Scenario: Completeness flag
- **WHEN** la integración marca `provider_report` como completa
- **THEN** el lote incrementa su versión y registra auditoría

### Requirement: RF-04 Deterministic exact matching

El motor `rules/v1` SHALL agrupar observaciones admitidas por referencia fuerte acotada y tipo de operación. Un match EXACT MUST exigir candidato único en cada fuente, dinero idéntico (tolerancia cero) y estado igual. Diferencias de importe o estado con referencia compartida MUST producir un resultado `UNMATCHED` con todas las discrepancias enlazadas. Importe y hora por sí solos MUST NOT justificar un match exacto, y ninguna comparación cruza tenant, cuenta, moneda ni operación.

#### Scenario: Amount mismatch of 100
- **WHEN** el ledger tiene USD 100.00 y el proveedor USD 99.00 con la misma referencia
- **THEN** el resultado es `UNMATCHED` con `AMOUNT_MISMATCH` y diferencia `-100` unidades menores

#### Scenario: Cross currency
- **WHEN** la misma referencia aparece en USD y BOB
- **THEN** no hay match; cada lado se reporta en su lote

### Requirement: RF-05 Explainable weak ranking with preserved ambiguity

Las observaciones sin contraparte fuerte SHALL rankearse con reglas explicables (attempt_ref, importe, ventana de una hora) cuyo puntaje es un ranking y no una probabilidad. Un único mejor candidato recíproco MUST producir `PROBABLE` con alternativas; un empate MUST conservarse como ambigüedad sin elegir.

#### Scenario: Tied candidates
- **WHEN** dos observaciones externas empatan como mejor candidato
- **THEN** el resultado queda `UNMATCHED` con regla `weak_ambiguous` y ambas alternativas

### Requirement: RF-06 Missing only after cutoff and completeness

Una observación sin contraparte MUST reportarse como `WAITING_SOURCE` mientras el lote no alcance el cutoff o la fuente contraria no esté completa, y como `MISSING_INTERNAL`/`MISSING_EXTERNAL` sólo después de ambos.

#### Scenario: Open window
- **WHEN** se ejecuta un run antes del cutoff
- **THEN** los faltantes se reportan como `WAITING_SOURCE`

### Requirement: RF-07 Duplicates and processing errors

Varias observaciones de una misma fuente con la misma referencia SHALL producir `DUPLICATE_CANDIDATE` sin forzar match ni deduplicar dinero. Una referencia con filas en cuarentena SHALL producir `PROCESSING_ERROR` con `NOT_EVALUATED`.

#### Scenario: Two provider charges with the same reference
- **WHEN** el proveedor reporta dos registros distintos con la misma referencia
- **THEN** el resultado es `NOT_EVALUATED` con `DUPLICATE_CANDIDATE`

### Requirement: RF-08 Reproducible versioned runs

Cada run SHALL evaluar la revisión vigente de cada observación del alcance, guardar ruleset, snapshot hash, conteos y resultados ordenados establemente, y producir el mismo resultado ante el mismo snapshot sin importar el orden de entrada. Un rerun MUST crear una versión nueva y MUST NOT modificar resultados anteriores.

#### Scenario: Late arrival
- **WHEN** llega una observación después de un run y se solicita otro
- **THEN** el run 2 tiene otro snapshot hash y el run 1 conserva sus resultados

### Requirement: RF-09 Reliable event publication and consumption

Cada comando SHALL persistir estado, auditoría y outbox en una transacción; un relay MUST publicar en JetStream con ID estable; los consumidores MUST deduplicar con inbox o clave de idempotencia en la misma transacción que el efecto; mensajes malformados o agotados MUST enviarse a un stream de dead letters con razón.

#### Scenario: Redelivered run request
- **WHEN** el mismo evento `ReconciliationRequested` se entrega dos veces
- **THEN** el run se ejecuta una sola vez y la segunda entrega es no-op

#### Scenario: Poison event
- **WHEN** llega un evento de ingestion malformado
- **THEN** se envía a `RECON_DLQ` y no se reintenta

### Requirement: RF-10 Authenticated, role-based versioned API

Las rutas `/v1` SHALL exigir un JWT RS256 válido (emisor, audiencia, expiración y clave conocida) y un rol permitido por ruta: `integration` ingiere y marca completitud, `analyst` crea lotes y solicita runs, y `analyst`/`supervisor`/`auditor` leen. Recursos de otro tenant MUST responder 404. El catálogo de rutas MUST ser exactamente el declarado, sin operaciones de movimiento de dinero ni de agentes.

#### Scenario: Wrong role
- **WHEN** un analista intenta ingerir un artefacto
- **THEN** recibe 403 antes de tocar almacenamiento

#### Scenario: Missing token
- **WHEN** una petición no trae bearer token
- **THEN** recibe 401

### Requirement: RF-11 No AI in the deterministic path

La ingestion, el motor de reglas, la persistencia y el worker MUST NOT importar ni invocar clientes de modelos o HTTP salientes; los matches exactos cuestan cero llamadas generativas.

#### Scenario: Import audit
- **WHEN** se analizan los imports de dominio, store y worker
- **THEN** no aparece ningún cliente de modelos ni HTTP
