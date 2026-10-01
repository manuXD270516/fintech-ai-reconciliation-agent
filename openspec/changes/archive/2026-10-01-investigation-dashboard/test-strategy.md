# Estrategia de pruebas — M8

Contrato OpenAPI en Python, componentes con Vitest + Testing Library, gate `web` (tipos generados, `tsc`, Vitest, build) y E2E Playwright contra el stack real dentro del smoke.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Contrato | `tests/unit/test_openapi_contract.py`: `apps/web/openapi.json` idéntico al de la app y modelos de casos tipados; `npm run check:api` (`openapi-typescript --check`) |
| T02 | Rutas de lectura | `tests/unit/test_scope.py` con el catálogo exacto incluido `/v1/batches`, `/v1/batches/{id}/runs`, `/v1/cases`; ejercitadas en el E2E |
| T03 | Borrador | `DraftView`: tres regiones con nombre, citas resueltas o "cita no resuelta", evidencia necesaria de hipótesis, `uncalibrated`, `SIMULATED`, advertencia de contenido no confiable y revisión que no es aprobación (`apps/web/src/test/components.test.tsx`) |
| T04 | Decisión | Efecto exacto visible, motivo obligatorio, versión e idempotencia enviadas; caso obsoleto deshabilita (mismo archivo) |
| T05 | Errores | Mensajes por código (segregación, obsolescencia, versión) y nada de detalles internos ante 500 (mismo archivo) |
| T06 | Teclado | Formulario de decisión completo por teclado; detalle de resultado abierto con Tab + Enter (mismo archivo) |
| T07 | E2E real | Smoke `M8-T07` (`scripts/web_e2e.py` + `apps/web/e2e/flow.spec.ts`): analista abre el resultado por teclado, pide investigación (DRAFTED, tres secciones, SIMULATED, uncalibrated), abre caso y propone adoptando el borrador; proponente con rol supervisor rechazado; supervisor ve "Vigente", decide por teclado; auditor ve `decision.record`, `decision.denied` e `investigation.finish`; axe sin violaciones serias/críticas en investigación y caso |
| T08 | Gate | `scripts/gate.py all` con el paso `web` y paridad de CI |

## Ejecución y evidencias

`uv run python scripts/gate.py all`. Evidencia en [evidence/](evidence/README.md). Las salidas del modelo en la UI son SIMULATED.

## Stop condition

M8 no agrega IdP real, despliegue ni acciones con efectos financieros.
