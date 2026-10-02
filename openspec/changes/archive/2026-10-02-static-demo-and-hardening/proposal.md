## Why

El repositorio ya es público y su CI corre. El propietario pidió dos cosas:

1. Publicar en GitHub Pages lo que se pueda publicar.
2. Cerrar los pendientes que dejaron M9 y M10 sin usar cuentas pagas:
   - dos alertas verificadas sólo con tests unitarios;
   - el runbook de rollback de ruleset sin ejercitar;
   - la falta de escaneo de dependencias;
   - la falta de un escáner externo de secretos.

## What Changes

- **Demo estática en GitHub Pages:** el dashboard compilado con `VITE_DEMO_MODE=1`.
  - Responde los GET desde un fixture JSON capturado de una ejecución real local sobre datos sintéticos (`scripts/capture_demo_fixtures.py`).
  - Rechaza toda mutación con `demo_read_only`.
  - Ofrece sesiones de sólo lectura sin firma (analista, supervisora, auditor).
  - El workflow `pages` publica con `actions/upload-pages-artifact` y `actions/deploy-pages` (fijadas por SHA), sólo después de que el workflow `ci` pase sobre el mismo commit, y bloquea el bundle si contiene JWT, hosts locales o rutas personales.
- **Alertas en vivo (smoke `M11-T02`):**
  - `HumanBacklog`: dispara con una recomendación antedatada y vuelve al estado base al resolverla.
  - `ToolPermissionRefused`: dispara con un rechazo real de una tool MCP por scope.
- **Rulesets versionados:**
  - `APP_RULESET` elige el ruleset de los runs nuevos.
  - Cada run conserva el suyo y se ejecuta con él.
  - `rules/v2` es una variante **sintética** sin ranking débil.
  - El smoke `M11-T03` ejercita el runbook de rollback v2 → v1.
- **Supply chain:**
  - Workflow `security` con gitleaks v8.30.1 sobre toda la historia (allowlist revisada en `.gitleaksignore`), `pip-audit` sobre `uv.lock` y `npm audit` sobre ambos lockfiles.
  - Dependabot semanal.
- **Historia:** las rutas locales que siguen en commits antiguos se documentan; no se reescribe la historia.

## Capabilities

### New Capabilities

- `static-demo-and-hardening`: demo pública estática y endurecimiento operativo y de supply chain.

### Modified Capabilities

Ninguna spec vigente cambia de comportamiento. `rules/v1` sigue por defecto y la API sólo agrega configuración (`APP_RULESET`).

## Impact

`apps/web` (modo demo, fixture), `packages/domain` y `packages/store` (selección de ruleset), API (configuración), `scripts/` (captura, drills), `.github/` (workflows `pages` y `security`, Dependabot), runbooks y revisión de seguridad.

## Non-goals

Backend público, cuentas pagas, claves reales, reescritura de historia y un ruleset nuevo "mejor": `rules/v2` es sólo un drill.
