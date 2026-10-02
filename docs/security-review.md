# Revisión de seguridad (M9)

Revisión interna del 2026-10-01 sobre el stack local `recon-m0`. No es una auditoría externa ni un pentest. Alcance: autenticación y autorización de la API, aislamiento entre tenants, privilegios de base de datos, superficie de observabilidad, secretos e historia git. Cada conclusión enlaza el test o la evidencia que la respalda. Lo que no se verificó figura en **Pendiente**.

## Autenticación y autorización (API)

- JWT RS256 contra un JWKS local, con issuer, audiencia, expiración y `kid` verificados. Se rechazan claves ajenas, `alg=none` y roles desconocidos (`tests/unit/test_auth.py`). Si no hay verificador, la API responde 503 (falla cerrada).
- **Matriz ruta × rol:** `tests/unit/test_access_matrix.py` declara los roles de cada una de las 18 rutas `/v1`. Comprueba que sin token se responde 401, que cada rol fuera del conjunto recibe 403 antes de tocar almacenamiento y que los roles permitidos superan la autorización. El test falla si aparece una ruta sin declarar.
- `POST /v1/cases/{id}/decisions` admite roles de lectura en la capa HTTP **a propósito**: así el servicio puede auditar los intentos rechazados (`decision.denied` con `role_not_allowed`, `segregation_of_duties`, `version_conflict`). Sólo decide un supervisor que no propuso ni pidió la investigación. Lo verifican los tests de integración de M6 y el smoke `M6-T08`.
- **Rutas públicas:** `/health/live`, `/health/ready`, `/docs`, `/openapi.json` y `/metrics`. Ninguna devuelve datos de identidad, tenant, hosts ni secretos (`tests/unit/test_scope.py`, `tests/unit/test_observability.py` y smoke `T05`/`M9-T04`).

## Aislamiento entre tenants

El tenant sale siempre del token o, en eventos, del sujeto NATS; nunca del cuerpo del mensaje. Tests:
- `test_tenant_isolation_on_reads` (lecturas de conciliación).
- `test_body_cannot_override_subject_tenant` (ingestion por eventos).
- `test_other_tenant_cannot_read_investigations`.
- `test_rg04_other_tenant_content_is_never_exposed` (retrieval).
- `test_other_tenant_resources_are_indistinguishable_from_missing` (MCP).

## Privilegios

- **`recon_app`:** sin SUPERUSER, CREATEDB ni CREATEROLE. Tiene `SELECT, INSERT` por tabla y `UPDATE` sólo sobre columnas concretas. Auditoría y observaciones son append-only por permisos. En M9 sólo se agregó `service_heartbeats` (`SELECT, INSERT` y `UPDATE (instance, beat_at)`).
- **`recon_mcp`:** `SELECT` sobre las tablas de evidencia e `INSERT` en auditoría. Lo verifica el test de integración del rol MCP.
- **Contenedores de la aplicación:** sin root, con filesystem de sólo lectura, `cap_drop: ALL` y `no-new-privileges`. PostgreSQL y NATS no publican puertos; sólo la API (`127.0.0.1:18180`) y, en el perfil opcional, Jaeger (`127.0.0.1:18186`). Lo verifica el smoke `T08`.

## Secretos

- `.env`, `.dev-keys/` y `.backups/` están en `.gitignore`. `.env.example` sólo contiene marcadores `dev-only-*`, lo que verifica el paso `policy`.
- **Escaneo de historia (paso `secrets`):** `scripts/secret_scan.py` revisa todas las líneas agregadas en cada commit alcanzable desde cualquier ref. Busca claves privadas, claves AWS, OpenAI, Anthropic, Google y Stripe, tokens de GitHub y Slack, JWT, credenciales en URL y números tipo PAN con Luhn válido, además de rutas prohibidas en la historia. Resultado: 0 hallazgos (ver la evidencia de `observability-security`). Es heurístico. Desde M11 también corre **gitleaks v8.30.1** sobre toda la historia en el workflow `security`. Encontró 2 falsos positivos revisados por el propietario (el canario de tests y una línea de prosa), que quedan en `.gitleaksignore`.
- Las variables de credenciales de IA se eliminan del entorno de cada paso del gate. Ningún test usa claves reales.

## Hallazgos

| ID | Hallazgo | Severidad (local / si se publicara) | Estado |
|---|---|---|---|
| S1 | `/metrics` no exige autenticación y expone conteos agregados de todos los tenants (sin IDs) | Baja / Media | Aceptado en local: sólo loopback, etiquetas de baja cardinalidad verificadas. Si se publicara, poner `/metrics` detrás de la red interna o de autenticación |
| S8 | Demo estática en GitHub Pages (M11) | Baja | Sólo HTML/JS y un fixture JSON con datos sintéticos capturados en local. No hay backend ni tokens: las sesiones son de sólo lectura y no están firmadas. El workflow `pages` verifica que el bundle no contenga JWT, hosts locales ni rutas personales |
| S2 | Jaeger UI sin autenticación (perfil `observability`) | Baja / Alta | Apagado por defecto y sólo en loopback. Los spans no llevan tenant, sujeto ni montos (verificado en el demo) |
| S3 | La sesión del dashboard usa un JWT de desarrollo pegado a mano y guardado en `sessionStorage` | N/A / Alta | Diseño sólo para desarrollo; un despliegue requeriría OIDC (fuera de alcance, D10) |
| S4 | La API HTTP no tiene rate limiting (MCP sí lo tiene) | Baja / Media | Pendiente; documentado |
| S5 | Faltaba un escaneo de vulnerabilidades de dependencias | — / Media | Resuelto en M11. El workflow `security` (cada push, PRs y semanal) corre `pip-audit` sobre `uv.lock` y `npm audit --audit-level=high` sobre ambos lockfiles, y Dependabot abre PRs semanales (uv, npm, actions, docker). Primera ejecución local: 0 vulnerabilidades conocidas |
| S6 | El escáner propio de secretos es heurístico | Baja | Mitigado en M11 con gitleaks en el workflow `security` y allowlist revisada. Las rutas locales de logs antiguos siguen en la historia pública: el propietario decidió no reescribirla |
| S7 | Los dead letters guardan el payload original (datos sintéticos) durante 7 días | Baja | Aceptado: datos sintéticos; el triage queda auditado |

No hay cifrado en reposo ni TLS interno: es un stack local sobre una red Docker `internal`. No hay movimiento de dinero ni integraciones reales.
