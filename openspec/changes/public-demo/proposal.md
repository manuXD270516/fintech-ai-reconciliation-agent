## Why

M10 prepara la demo para que un tercero la pueda reproducir y evaluar con honestidad. Eso exige un walkthrough reproducible desde un clone limpio, una ficha del dataset, un documento de resultados sanitizado con los límites a la vista, una revisión de secretos, datos y licencias, aislamiento entre sesiones de demo y un kill switch de IA que deje operativa la ruta determinística. Por D10, **no** se publica el repositorio ni se despliega nada.

## What Changes

- **Sesiones de demo** (`scripts/demo.py seed`): cada sesión es un tenant nuevo, con el dataset `transactions-v2` ingerido por HTTP, los 12 lotes ejecutados y los resultados comparados con las etiquetas. Los tokens de la sesión quedan en `.demo/` (ignorado por git).
- **Kill switch de IA** (`APP_AI_ENABLED`, `scripts/demo.py kill-switch on|off`):
  - Con el switch apagado, `POST …/investigations` responde 503 con `{"code": "ai_disabled"}`.
  - Conciliación, casos, propuestas sin borrador y decisiones siguen funcionando.
  - El estado del switch se expone en `recon_ai_enabled` y el dashboard muestra el mensaje.
- **Documentación de la demo:** `docs/demo/walkthrough.md`, `docs/demo/results.md` (resultados sanitizados con etiquetas MEASURED/SIMULATED/EXPECTED, costos y decisiones pendientes) y la ficha `datasets/README.md`.
- **Revisión previa a publicar:**
  - Inventario offline de licencias de terceros (`scripts/license_inventory.py`).
  - El paso `policy` falla ante rutas de perfil de usuario en el árbol; se redactaron 3 logs de evidencia de M0/M1.
  - `.demo/` se agrega a las rutas prohibidas del escaneo de secretos.
  - Medición de recursos (`scripts/demo.py resources`).
- **Smoke** `M10-T03`: dos sesiones aisladas entre sí y el flujo humano completo con la IA apagada, que vuelve a funcionar al reactivarla.

## Capabilities

### New Capabilities

- `public-demo`: demo local reproducible y aislada, con kill switch de IA y documentación sanitizada, sin publicación.

### Modified Capabilities

Ninguna en specs vigentes. La API agrega la configuración `APP_AI_ENABLED`, encendida por defecto y sin cambio de comportamiento.

## Impact

`apps/api` (configuración y ruta de investigación), `apps/web` (mensaje del switch), `compose.yaml`, `scripts/` (demo, inventario de licencias, política), `docs/demo/` y `datasets/README.md`. Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md) (D10).

## Non-goals

Hacer público el repositorio, desplegar, crear cuentas o recursos en la nube, elegir una licencia por el propietario, reescribir la historia git y medir la calidad de un LLM real.
