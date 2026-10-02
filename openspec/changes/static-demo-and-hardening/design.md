## Context

El repo es público y tiene CI gratis. El propietario autorizó GitHub Pages y pidió cerrar los pendientes sin cuentas pagas. Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md).

## Decisions

- **Demo estática como modo del mismo dashboard**, no como un sitio aparte.
  - Un middleware de `openapi-fetch` responde desde `public/demo/fixtures.json`. Los GET se filtran como en la API (`match_status`, `status`, auditoría restringida por rol). Las mutaciones devuelven 403 `demo_read_only`, salvo las reaperturas idempotentes capturadas (abrir el caso o la investigación existentes).
  - Las sesiones son tokens sin firma generados en el navegador con `alg: none` y firma literal `demo`. No son credenciales ni se versionan.
  - El fixture se regenera con `scripts/capture_demo_fixtures.py` contra el stack local. Ese script falla si el fixture contiene JWT, hosts locales o rutas personales.
- **Pages después del gate.** El workflow `pages` se dispara por `workflow_run` del workflow `ci` en `main`, sólo si concluyó en `success`, y hace checkout del mismo `head_sha`. Antes de subir el artefacto vuelve a correr Vitest y un grep de contenido prohibido sobre el bundle.
- **Drills de alertas sin tocar código de producción.**
  - La recomendación antedatada se inserta con el grant `INSERT` del rol runtime y se marca `SUPERSEDED` con su `UPDATE (status)`.
  - Si el stack local ya tenía trabajo viejo pendiente (por ejemplo, el que dejan los tests de integración), el drill antedata más allá de esa base y verifica que la antigüedad máxima es la suya.
  - `ToolPermissionRefused` usa una identidad MCP sin `knowledge:read`. Su ventana de auditoría de 1 h hace que siga activa después del drill: `M9-T04` la reporta, pero no la cuenta como falla.
- **Rulesets.** `reconcile(inp, version)` recibe la versión registrada en el run, así que un run nunca cambia de reglas. `rules/v2` desactiva el ranking débil y queda declarado como SYNTHETIC. `APP_RULESET` sólo admite versiones conocidas.
- **Supply chain fuera del gate offline.** `scripts/gate.py` sigue sin red. El workflow `security` corre gitleaks por imagen fijada por digest (sin descargar binarios en local), `pip-audit` 2.10.0 vía `uvx` y `npm audit --audit-level=high`. Dependabot no hace merge automático.

## Risks / Trade-offs

- El fixture es una foto: puede quedar desactualizado frente a la API. El test de contrato OpenAPI no lo cubre, así que debe recapturarse al cambiar los modelos de respuesta.
- `pip-audit` y `npm audit` dependen de bases públicas de advisories: un aviso nuevo puede poner el workflow en rojo sin cambios en el repo. Ese es el comportamiento buscado.
