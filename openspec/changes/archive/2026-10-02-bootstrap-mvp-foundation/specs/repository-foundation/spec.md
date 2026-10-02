## Purpose

Permitir a un contributor preparar y verificar una base local segura y reproducible para desarrollar conciliación e investigación asistida, sin datos reales ni credenciales de proveedores externos.

## ADDED Requirements

### Requirement: RF-01 Reproducible contributor setup

El repositorio SHALL documentar prerrequisitos con versiones soportadas y proveer dependencias fijadas y comandos de instalación sin cuentas financieras ni credenciales IA. Un checkout limpio MUST poder ejecutar el bootstrap sin herramientas globales no declaradas.

#### Scenario: Clean supported environment
- **WHEN** un contributor sigue la guía desde un checkout limpio con los prerrequisitos soportados
- **THEN** instala las dependencias fijadas y obtiene comandos de arranque y validación ejecutables sin secretos externos

#### Scenario: Unsupported prerequisite
- **WHEN** falta un prerrequisito o su versión no es soportada
- **THEN** la guía o verificación identifica el requisito faltante y una acción de corrección sin afirmar que el setup esté listo

### Requirement: RF-02 Local lifecycle and persistence

El entorno SHALL permitir iniciar API y dependencias locales, comprobar persistencia, capacidad vectorial y mensajería durable, y detener servicios sin borrar datos por defecto. Cualquier reset destructivo MUST estar separado y descrito explícitamente.

#### Scenario: Successful startup
- **WHEN** el contributor inicia el entorno con configuración válida
- **THEN** API y dependencias reportan su estado, la capacidad vectorial está disponible y un smoke confirma publicación y consumo durable de un mensaje sintético

#### Scenario: Non-destructive stop
- **WHEN** el contributor detiene y reinicia el entorno sin solicitar reset
- **THEN** un marcador persistido y un mensaje pendiente sobreviven al reinicio

### Requirement: RF-03 Liveness and readiness

La API SHALL exponer `GET /health/live` para salud del proceso y `GET /health/ready` para dependencias requeridas. Liveness MUST responder 200 mientras el proceso sirve solicitudes. Readiness MUST responder 200 sólo si persistencia, capacidad vectorial y mensajería durable están listas, o 503 si alguna falla, dentro de un timeout total de 3 segundos.

#### Scenario: All dependencies ready
- **WHEN** el proceso responde y sus tres capacidades requeridas están disponibles
- **THEN** ambas rutas responden 200 y readiness identifica cada capacidad sin credenciales ni detalles internos sensibles

#### Scenario: Dependency unavailable
- **WHEN** persistencia o mensajería no responde, o falta capacidad vectorial
- **THEN** liveness sigue en 200 si el proceso funciona y readiness responde 503 en no más de 3 segundos, sin stack traces ni connection strings

### Requirement: RF-04 Safe local configuration

El bootstrap SHALL usar configuración y fixtures sintéticos de desarrollo, ignorar secretos locales en control de versiones y restringir exposición por defecto a loopback. Configuración obligatoria inválida MUST impedir arranque con diagnóstico sanitizado. Health checks MUST funcionar sin claves LLM.

#### Scenario: Default developer startup
- **WHEN** se usa la configuración de ejemplo
- **THEN** sólo se expone la API local, las dependencias no están accesibles desde interfaces públicas y no se requieren credenciales reales

#### Scenario: Missing required configuration
- **WHEN** falta configuración obligatoria o es inválida
- **THEN** el proceso termina con error y nombra el campo a corregir sin imprimir su valor secreto

### Requirement: RF-05 Minimal diagnostic traceability

La API SHALL devolver `X-Request-ID` no sensible en health responses y emitir logs estructurados correlacionando método, ruta, status y duración. Los logs MUST excluir secretos y payloads innecesarios.

#### Scenario: Health request correlation
- **WHEN** se ejecuta un health check
- **THEN** respuesta y log comparten un request ID válido y muestran resultado y duración sin valores secretos

### Requirement: RF-06 Repeatable quality gate

El repositorio SHALL ofrecer verificaciones locales y CI equivalente que cubran estilo, tipos, tests de health/configuración, smoke de dependencias y validación estricta OpenSpec. El gate MUST fallar ante errores y funcionar sin credenciales de servicios IA.

#### Scenario: Valid foundation
- **WHEN** se ejecuta el gate sobre bootstrap válido y dependencias locales
- **THEN** produce evidencia para todos los checks sin invocar servicios financieros ni modelos externos

#### Scenario: Broken contract
- **WHEN** un test de contrato falla o una spec no valida
- **THEN** comandos locales y CI reportan fallo con código de salida distinto de cero

### Requirement: RF-07 Scope and evidence honesty

La documentación SHALL distinguir implementado y planeado, prohibir datos/secretos reales en ejemplos y diferenciar MEASURED, SIMULATED y EXPECTED. Bootstrap MUST exponer únicamente salud y documentación técnica de API, sin endpoints operativos de pagos o aprobación.

#### Scenario: M0 scope inspection
- **WHEN** se consulta README y catálogo de rutas M0
- **THEN** se identifica sólo bootstrap y no se anuncian conciliación, MCP, agentes o ejecución financiera como operativos

#### Scenario: Unmeasured target
- **WHEN** se presenta un objetivo de precisión, latencia o tokens sin ejecución respaldada
- **THEN** se etiqueta EXPECTED y no se publica como resultado medido

### Requirement: RF-08 Specification traceability

Todo change sustancial SHALL incluir proposal, requirements con escenarios, acceptance criteria, design, tasks verificables y test strategy antes de implementar. Tasks MUST reflejar evidencia real y specs vigentes MUST actualizarse sólo al integrar un change implementado y verificado.

#### Scenario: Change ready for implementation review
- **WHEN** se revisa un change para comenzar implementación
- **THEN** existen los seis artefactos y cada criterio de aceptación apunta a requisitos, pruebas previstas y tareas

#### Scenario: Specification without implementation
- **WHEN** sólo se han escrito y validado artefactos de diseño
- **THEN** las tareas de implementación siguen pendientes y el change no se archiva como capacidad implementada
