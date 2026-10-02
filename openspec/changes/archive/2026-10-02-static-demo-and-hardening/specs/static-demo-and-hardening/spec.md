## ADDED Requirements

### Requirement: RF-01 Static read-only public demo

El repositorio SHALL publicar en GitHub Pages un dashboard estático que lea un fixture capturado de una ejecución local sobre datos sintéticos. El dashboard MUST NOT tener backend y MUST rechazar toda mutación como de sólo lectura. El despliegue MUST ocurrir sólo después de que el gate de CI pase sobre el mismo commit y MUST bloquearse si el bundle contiene tokens, hosts locales o rutas personales.

#### Scenario: Read-only visitor
- **WHEN** un visitante entra como supervisora e intenta registrar una decisión
- **THEN** ve el mensaje de demo de sólo lectura y nada se envía a ningún servidor

### Requirement: RF-02 Live alert drills

Las alertas `HumanBacklog` y `ToolPermissionRefused` SHALL dispararse en vivo en el smoke con fallas inyectadas sólo en tenants de drill. Al resolver la falla, `HumanBacklog` MUST volver al estado base. Ningún drill MUST dejar trabajo pendiente en la cola humana.

#### Scenario: Backdated recommendation
- **WHEN** existe una recomendación pendiente con más de 24 h
- **THEN** `HumanBacklog` dispara, y vuelve al estado base al resolverla

### Requirement: RF-03 Versioned rulesets and rollback

El ruleset de los runs nuevos SHALL elegirse al desplegar. Cada run MUST registrar su ruleset y ejecutarse con él. Un rollback MUST NOT reescribir runs existentes y MUST dejar obsoletas las recomendaciones del run anterior.

#### Scenario: Rollback v2 to v1
- **WHEN** un lote corrido con `rules/v2` se vuelve a correr tras volver a `rules/v1`
- **THEN** el run nuevo tiene el mismo snapshot y recupera los PROBABLE, el run v2 queda intacto y decidir sobre su recomendación devuelve `recommendation_obsolete`

### Requirement: RF-04 Supply-chain scanning

El CI SHALL escanear toda la historia con gitleaks y las dependencias bloqueadas con pip-audit y npm audit, y MUST fallar ante hallazgos no revisados. Los falsos positivos MUST quedar en una allowlist comentada.

#### Scenario: New leak
- **WHEN** un commit agrega un secreto
- **THEN** el workflow `security` falla

### Requirement: RF-05 History disclosure without rewrite

Las rutas locales presentes en commits antiguos SHALL documentarse como riesgo aceptado, y la historia MUST NOT reescribirse.

#### Scenario: Reader checks the limits
- **WHEN** un lector revisa la revisión de seguridad
- **THEN** encuentra el hallazgo y la decisión de no reescribir la historia
