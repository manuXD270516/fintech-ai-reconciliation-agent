## ADDED Requirements

### Requirement: RF-01 Reproducible, isolated demo sessions

El repositorio SHALL ofrecer un comando que cree una sesión de demo en un tenant propio, ingiera el dataset sintético por la API, ejecute todos sus lotes y verifique los resultados contra las etiquetas. Una sesión MUST NOT poder leer los datos de otra.

#### Scenario: Two sessions
- **WHEN** se crean dos sesiones y la primera consulta un run de la segunda
- **THEN** recibe 404 y su listado de lotes contiene sólo los propios

### Requirement: RF-02 AI kill switch

Con `APP_AI_ENABLED=false`, la API SHALL rechazar nuevas investigaciones con 503 y el código `ai_disabled`, después de autenticar y autorizar. La conciliación, la apertura de casos, las propuestas sin borrador y las decisiones humanas MUST seguir funcionando. El estado MUST exponerse en `/metrics`.

#### Scenario: Human path without AI
- **WHEN** con el switch apagado un analista propone sin borrador y una supervisora aprueba
- **THEN** la decisión se registra sin efecto operativo y un nuevo run determinístico se completa

### Requirement: RF-03 Walkthrough and dataset card

El repositorio SHALL incluir un walkthrough reproducible desde un clone limpio y una ficha de datasets con origen, versión, semilla o generador, conteos, hashes y limitaciones. Ambos MUST declarar lo que la demo no demuestra.

#### Scenario: Visible limitations
- **WHEN** un lector abre el walkthrough
- **THEN** encuentra que las salidas de IA son SIMULATED y que el sistema no está listo para producción

### Requirement: RF-04 Sanitized results and pre-publication review

El documento de resultados SHALL enlazar la evidencia de cada capacidad con su etiqueta (MEASURED/SIMULATED/EXPECTED), los costos y recursos medidos y las decisiones pendientes del propietario. El árbol MUST NOT contener rutas de perfil de usuario (paso `policy`) ni secretos en la historia (paso `secrets`). Un inventario de licencias de terceros MUST señalar las que requieren revisión.

#### Scenario: Personal path in evidence
- **WHEN** un archivo versionado contiene una ruta `C:\Users\<nombre>`
- **THEN** el paso `policy` falla

### Requirement: RF-05 No publication

M10 MUST NOT hacer público el repositorio, desplegar ni crear recursos en la nube. Push, PRs, licencia y reescritura de historia SHALL quedar documentados como decisiones del propietario.

#### Scenario: Pending decisions
- **WHEN** se cierra M10
- **THEN** el documento de resultados lista licencia, historia git, escáner externo y push/CI como decisiones pendientes
