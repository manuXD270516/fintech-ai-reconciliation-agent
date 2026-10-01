## Why

Las decisiones humanas de M6 hoy sólo son posibles por API. M8 entrega la interfaz para el flujo analista → supervisor: ver lotes, runs y resultados, pedir una investigación, leer el borrador separando hechos, inferencias e hipótesis con sus citas, proponer una recomendación y decidir sobre la versión vigente, con errores claros y operable por teclado. La UI no agrega permisos: todo se autoriza en la API.

## What Changes

- **App `apps/web`** (D08): Vite + React + TypeScript, CSS propio, cliente tipado generado desde OpenAPI (`openapi-typescript` + `openapi-fetch`), Vitest + Testing Library y Playwright; dependencias con versiones exactas y lockfile.
- **Vistas:** sesión de desarrollo (token de `scripts/dev_auth.py`), lotes, runs, resultados con filtro y detalle, investigación con timeline de pasos y borrador (FACT/INFERENCE/HYPOTHESIS, citas con localizador y vigencia, revisión, `uncalibrated`, etiqueta SIMULATED, advertencias de contenido no confiable), caso con banner de vigencia, propuesta de recomendación, formulario de decisión con el efecto exacto y sin aprobación masiva, traza de auditoría y cola de casos.
- **API de lectura para navegación:** `GET /v1/batches`, `GET /v1/batches/{id}/runs`, `GET /v1/cases` y modelos tipados de casos y auditoría en OpenAPI; el documento se exporta a `apps/web/openapi.json` con chequeo de drift.
- **Calidad:** paso de gate `web` (tipos generados al día, `tsc`, Vitest, build) en CI; E2E Playwright analista → supervisor → auditor contra el stack real dentro del smoke (`M8-T07`), con pasos por teclado y chequeo axe (WCAG 2 A/AA) sin violaciones serias o críticas.

## Capabilities

### New Capabilities

- `investigation-dashboard`: interfaz web accesible para investigar excepciones y registrar decisiones humanas sobre la API autorizada.

### Modified Capabilities

Ninguna en specs vigentes; la API agrega tres rutas de lectura y modelos de respuesta (sin cambios de comportamiento de escritura).

## Impact

`apps/web` (paquete npm propio), `scripts/export_openapi.py`, `scripts/web_e2e.py`, paso de gate `web`, instalación de dependencias web y Chromium de Playwright en CI, rutas `/v1` de lectura.

Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md) (D08).

## Non-goals

IdP real/OIDC en el navegador, despliegue público, i18n, modo oscuro, gráficos y cualquier acción que mueva dinero o apruebe en lote.
