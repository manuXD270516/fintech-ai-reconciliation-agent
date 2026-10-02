# Evidencia — static-demo-and-hardening (M11)

## Local (2026-10-02, Windows 11 + Docker Desktop, rama `m11-static-demo-and-hardening`)

| Archivo | Contenido |
|---|---|
| [gate-all.log](gate-all.log) | `scripts/gate.py all`: 11 de 12 pasos en PASS. Incluye test (308 unit), web (Vitest 11/11, con 4 tests del modo demo), secrets (47 commits, 0 hallazgos) y smoke (26/26, con `M11-T02` y `M11-T03`). El paso `lint` falló sólo por formato: faltaba una línea en blanco en `scripts/ops_drills.py`. Se corrigió y se reejecutó: [gate-lint-rerun.log](gate-lint-rerun.log) en PASS |
| [smoke.json](smoke.json) | Detalle de los drills |

**`M11-T02`**
- Este stack local tenía trabajo pendiente real de más de 24 h, dejado por tests de integración del día anterior, así que `HumanBacklog` ya estaba activo. El drill antedató su copia por encima de esa base: la antigüedad máxima pasó de 89 460 s a 93 060 s, que es la copia del drill. Al resolverla volvió a 89 468 s, el estado base.
- `ToolPermissionRefused` disparó con un `FORBIDDEN` real (`search_provider_docs` sin `knowledge:read`), auditado en la ventana de 1 h.
- El CI parte de una base vacía y muestra el ciclo completo de disparo y limpieza (ver "Remoto").

**`M11-T03`**
- Con `rules/v2` (sintético), el run registra `rules/v2`, sin PROBABLE: UNMATCHED 5.
- Tras el rollback, `rules/v1` sobre el mismo snapshot da PROBABLE 1 y UNMATCHED 3.
- Los resultados del run v2 quedaron intactos.
- La decisión sobre la recomendación del run v2 devolvió 409 `recommendation_obsolete`.

**Supply chain local, previo al CI**
- gitleaks v8.30.1 (imagen fijada por digest) sobre la historia completa: 2 hallazgos. Ambos son falsos positivos revisados por el propietario: `CANARY_SECRET` de los tests y una línea de prosa del proposal de M0. Con `.gitleaksignore`, no quedan hallazgos.
- `pip-audit` 2.10.0 sobre `uv.lock`: no se conocen vulnerabilidades.
- `npm audit`: 0 vulnerabilidades en ambos lockfiles.

**Demo estática**
- `npm run build:pages` con `VITE_DEMO_MODE=1` y la base `/fintech-ai-reconciliation-agent/`, servido en local: entrada por rol, lotes, investigación DRAFTED con el borrador SIMULATED y auditoría restringida por rol.
- El fixture (55 respuestas) no contiene JWT, hosts locales ni rutas personales. Lo verifican el script de captura y el workflow `pages`.

## Remoto

Pendiente: runs `ci`, `security` y `pages` del push a `main`.
