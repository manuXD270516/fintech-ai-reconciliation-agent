# Evidencia — public-demo (M10)

Ejecución local en Windows 11 con Docker Desktop, el 2026-10-01, sobre la rama `m10-public-demo` (base `4f35581`; se agregaron después la evidencia y el estado del change). No es CI remoto: GitHub Actions no ejecuta jobs por el bloqueo de facturación. Nada se publicó, se desplegó ni se subió.

| Archivo | Contenido |
|---|---|
| [gate-all.log](gate-all.log) | `scripts/gate.py all`: los 12 pasos en PASS. Incluye test (305 unit), web (Vitest 7/7), secrets (38 commits, 0 hallazgos) y smoke (24/24, con 86 tests de integración) |
| [smoke.json](smoke.json) | Reporte del smoke con `M10-T03` |
| [secret-scan.json](secret-scan.json) | Escaneo de secretos de toda la historia |
| [license-inventory.json](license-inventory.json) | 314 paquetes de terceros: 0 GPL/AGPL o desconocidas, 19 de copyleft débil (LGPL/MPL) |
| [resources.json](resources.json) | Memoria y CPU de los contenedores en reposo, y tamaño de las imágenes |

## Por criterio

- **AC01:** dentro de `M10-T03` se crearon dos sesiones (`demo-<id>`). Cada una tiene 12 lotes y 44 pagos, con resultados iguales a las etiquetas (`matches_labels`). La primera sesión recibe 404 al leer un run de la segunda y su listado muestra sólo sus 12 lotes.
- **AC02:**
  - `M10-T03`, con el switch apagado: la investigación recibe 503 `{"code": "ai_disabled"}`; el caso se abre; la propuesta sin borrador y la decisión `APPROVE` de la supervisora se registran sin efecto operativo; un nuevo run determinístico se completa.
  - Al reactivar el switch, una investigación responde 202.
  - Tests unitarios: el 503 llega sólo después de 401/403, los runs no se bloquean, `recon_ai_enabled 0` y la configuración se lee del entorno.
  - Vitest: el dashboard muestra el mensaje del kill switch.
- **AC03:** `docs/demo/walkthrough.md` es reproducible desde un clone limpio; sus comandos `seed` y `kill-switch` se ejercitan en `M10-T03`. Explica qué no demuestra. `datasets/README.md` documenta origen, versiones, semillas, conteos, escenarios, separación del oráculo, límites y licencia pendiente.
- **AC04:**
  - `docs/demo/results.md` enlaza la evidencia de cada capacidad con su etiqueta e incluye costos (0 en APIs) y recursos medidos.
  - `policy` pasa con la regla nueva de rutas de perfil; se redactaron tres logs de M0/M1.
  - `secrets` pasa sobre toda la historia, y el inventario de licencias está en evidencia.
- **AC05:** no hubo push, PRs, deploys ni publicación. `results.md` documenta las decisiones pendientes: licencia, historia git con rutas locales en commits antiguos, escáner externo y push/CI. El gate completo está en PASS.

## Límites

- Las rutas locales redactadas siguen en commits anteriores: no se reescribió la historia.
- El inventario de licencias no es asesoramiento legal.
- Los recursos son una muestra puntual.
