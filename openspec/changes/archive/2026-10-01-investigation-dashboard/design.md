## Context

Implementa el dashboard de [docs/09-roadmap.md](../../../../docs/09-roadmap.md) (M8) con D08 de [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md) sobre la API de M2–M6.

## Goals / Non-Goals

**Goals:** flujo analista → supervisor completo, vigencia y efecto explícitos, errores claros, teclado y axe, contrato tipado.

**Non-Goals:** IdP real, despliegue, i18n.

## Decisions

- **Mismo origen.** Vite (dev y preview) sirve en `127.0.0.1:18181` y hace proxy de `/api` a `127.0.0.1:18180`; no se habilita CORS en la API ni se publica nada fuera de loopback.
- **Contrato.** `scripts/export_openapi.py` escribe `apps/web/openapi.json` desde la app real; un test Python falla ante drift y `openapi-typescript --check` falla si `schema.d.ts` no corresponde. Para que el contrato sea útil se agregan modelos de respuesta tipados a casos y auditoría y tres rutas de lectura para navegar (`/v1/batches`, `/v1/batches/{id}/runs`, `/v1/cases`).
- **Sesión de desarrollo.** El usuario pega un JWT de `scripts/dev_auth.py`; se guarda en `sessionStorage` y el payload se decodifica sólo para mostrar sujeto y roles. La autorización ocurre siempre en la API (los botones visibles por rol son una comodidad, no un control).
- **Ruteo por hash** sin dependencias (`#/runs/:id`, `#/investigations/:id`, `#/cases/:id`, `#/cases/:id/audit`). La investigación se consulta cada segundo hasta un estado terminal.
- **Decisiones.** Un formulario por recomendación pendiente; clave de idempotencia `web-<uuid>` por instancia del formulario (reintentos idempotentes); `expected_version` = versión mostrada; deshabilitado si el run no es el más reciente; texto del efecto exacto.
- **Accesibilidad.** HTML semántico (tablas con caption, regiones con encabezado, labels), foco visible de alto contraste, skip link, `role=alert`/`role=status`, `aria-live` en el estado de la investigación. Axe se ejecuta en el E2E sobre la investigación y el caso.
- **Pruebas.** Vitest + Testing Library para componentes puros (borrador, formulario de decisión, tabla por teclado, mensajes de error, sesión); Playwright contra el stack real orquestado por `scripts/web_e2e.py` (prepara lote y run nuevos, tokens y build) dentro del smoke.

## Risks / Trade-offs

- El E2E depende de Chromium instalado por Playwright; CI lo instala explícitamente antes del smoke.
- La sesión por token pegado no es apta para producción; un despliegue público requeriría OIDC y otro threat model (M10 no despliega).
