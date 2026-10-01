# Evidencia — investigation-dashboard (M8)

Ejecución local en Windows 11 + Docker Desktop, 2026-10-01, sobre el árbol de trabajo de la rama `m8-investigation-dashboard` (base `352a970`, cambios sin confirmar en ese momento: `dirty=true` en el smoke). No es CI remoto: GitHub Actions no ejecuta jobs por el bloqueo de facturación (AC06 de M0 sigue PENDING). Las salidas del modelo que muestra la UI son **SIMULATED** (proveedor scripted); no se llamó a ningún proveedor de IA externo.

| Archivo | Contenido |
|---|---|
| [gate-all.log](gate-all.log) | `uv run python scripts/gate.py all`: lock, lint, types, test (246 passed), policy, trace, openspec (9/9), negative, evals, **web** y smoke (19/19) en PASS |
| [smoke.json](smoke.json) | Reporte del smoke; `M8-T07` con run, pago y estadísticas de Playwright |
| [e2e-report.json](e2e-report.json) | Reporte JSON de Playwright del E2E (1 esperado, 0 inesperados, 0 flaky) |
| [vitest.log](vitest.log) | Vitest: 7 tests de componentes en PASS |

## Por criterio

- **AC01:** `tests/unit/test_openapi_contract.py` (en el paso `test`) compara `apps/web/openapi.json` con el OpenAPI de la app; el paso `web` corre `openapi-typescript --check` sobre `src/api/schema.d.ts` antes de `tsc` (gate-all.log, sección `web`).
- **AC02:** `tests/unit/test_scope.py` fija el catálogo de rutas con `/v1/batches`, `/v1/batches/{batch_id}/runs` y `/v1/cases`; el E2E navega lote → run → resultado usando sólo la API (smoke.json `M8-T07`).
- **AC03:** tests de `DraftView` en vitest.log (regiones de hechos, inferencias e hipótesis, citas, `uncalibrated`, SIMULATED, advertencia de contenido no confiable, revisión ≠ aprobación); el E2E espera `DRAFTED` y las tres secciones.
- **AC04:** tests de `DecisionForm` (efecto exacto, motivo obligatorio, versión e idempotencia, deshabilitado si es obsoleto); el E2E verifica "Vigente" y registra la decisión. No existe acción masiva en la UI.
- **AC05:** tests de `explain` (segregación de funciones, obsolescencia, versión; un 500 no muestra detalles internos); el E2E observa el rechazo por autoaprobación del proponente con rol supervisor.
- **AC06:** el E2E abre el resultado y registra la decisión sólo con teclado y ejecuta axe (`wcag2a`, `wcag2aa`) en investigación y caso sin violaciones serias o críticas; test de teclado en vitest.log.
- **AC07:** smoke `M8-T07` PASS (`expected: 1, unexpected: 0`): analista → rechazo de autoaprobación → supervisor aprueba → auditor ve `decision.record`, `decision.denied` e `investigation.finish`.
- **AC08:** paso `web` en `scripts/gate.py` (grupos `static` y `all`) y en `.github/workflows/ci.yml` (con `npm ci --prefix apps/web` e instalación de Chromium); test de paridad de CI en PASS; gate-all.log en PASS.

## Límites

- La sesión por JWT pegado es sólo para desarrollo local; no hay IdP real.
- La accesibilidad se verifica con axe y recorridos por teclado automatizados; no hubo una auditoría manual con lectores de pantalla.
- El E2E cubre un flujo feliz más el rechazo por segregación de funciones; los demás errores se cubren con pruebas de componente.
