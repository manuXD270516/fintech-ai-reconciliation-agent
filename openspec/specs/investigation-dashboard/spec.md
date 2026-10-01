# investigation-dashboard Specification

## Purpose
Dashboard web accesible para investigar excepciones y registrar decisiones humanas sobre la API autorizada, con cliente tipado desde OpenAPI.

## Requirements

### Requirement: RF-01 Client generated from the API contract

El cliente web SHALL generarse desde el documento OpenAPI de la API y MUST fallar el gate si el documento exportado o los tipos generados quedan desactualizados.

#### Scenario: Stale contract
- **WHEN** cambia un modelo de la API sin regenerar `openapi.json` o `schema.d.ts`
- **THEN** el test de contrato o el chequeo de tipos falla

### Requirement: RF-02 Navigation over authorized read models

La interfaz SHALL permitir navegar lotes, runs, resultados, investigaciones y casos usando sólo rutas de lectura autorizadas por la API, con el tenant del token y sin acceso directo a base de datos ni a modelos.

#### Scenario: Batches and runs
- **WHEN** un usuario autenticado abre la lista de lotes y un lote
- **THEN** ve sus runs ordenados y puede abrir los resultados de cada run

### Requirement: RF-03 Epistemic separation in the draft view

La vista de investigación SHALL mostrar estado, timeline de pasos y presupuesto, y el borrador en secciones separadas de hechos, inferencias e hipótesis con sus citas (localizador y vigencia), la evidencia faltante, la revisión independiente (aclarando que no es aprobación humana), la confianza `uncalibrated`, la etiqueta de origen del modelo y advertencias de contenido no confiable.

#### Scenario: Reviewed draft
- **WHEN** una investigación termina `DRAFTED`
- **THEN** la vista muestra las tres secciones, las citas resueltas y la etiqueta `SIMULATED`

### Requirement: RF-04 Human decision with explicit effect and validity

La vista de caso SHALL mostrar si el caso es vigente u obsoleto, permitir al analista proponer y al supervisor decidir sobre la versión vigente con motivo obligatorio y una clave de idempotencia, y MUST mostrar el efecto exacto de la decisión (sin movimiento de dinero). No MUST existir aprobación masiva y un caso obsoleto MUST deshabilitar la decisión.

#### Scenario: Obsolete case
- **WHEN** existe un run más nuevo del lote
- **THEN** la vista lo indica y el formulario de decisión queda deshabilitado

### Requirement: RF-05 Readable errors

Los errores de la API SHALL mostrarse como mensajes comprensibles por código (segregación de funciones, versión, obsolescencia, expiración, idempotencia, rol) sin exponer detalles internos del servidor.

#### Scenario: Self-approval attempt
- **WHEN** quien propuso intenta decidir
- **THEN** la interfaz muestra que no puede decidir sobre su propia propuesta

### Requirement: RF-06 Keyboard and assistive-technology access

Las acciones principales (abrir el detalle de un resultado, decidir) SHALL poder ejecutarse sólo con teclado, con foco visible, enlace para saltar al contenido, etiquetas en todos los controles, regiones con nombre y anuncios de estado; las páginas clave MUST NOT tener violaciones axe serias o críticas (WCAG 2 A/AA).

#### Scenario: Keyboard decision
- **WHEN** un supervisor completa el motivo y activa "Registrar decisión" con Enter
- **THEN** la decisión se registra y se anuncia el resultado

### Requirement: RF-07 End-to-end flow against the real stack

Un E2E SHALL recorrer en el stack real: analista pide investigación y propone adoptando el borrador revisado, el proponente con rol supervisor es rechazado, un supervisor aprueba y un auditor ve la traza con el intento rechazado y la decisión.

#### Scenario: Analyst to supervisor
- **WHEN** se ejecuta el E2E dentro del smoke
- **THEN** termina con la decisión registrada y la traza reconstruida
