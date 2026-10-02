# Decisiones de implementación M1–M10

Fecha: 2026-09-29. Decididas por el maintainer antes de la implementación autónoma de M1–M10. Cada change OpenSpec enlaza este archivo desde su `design.md` y cada PR incluye una checklist de cumplimiento. Una desviación sólo es válida si está registrada en la sección [Desviaciones](#desviaciones), eligiendo la opción más conservadora compatible con la decisión.

| # | Tema | Decisión |
|---|---|---|
| D01 | Alcance | M1→M6 (MVP técnico) con rigor completo, en orden de dependencias; si sobra tiempo, M7→M10 |
| D02 | OpenSpec | Un change por hito (proposal, specs con RF y escenarios, acceptance-criteria con Estado/Evidencia, design, tasks, test-strategy). Si todos sus AC pasan en local, se archiva y se promueve su spec sin preguntar. Los changes nuevos no incluyen AC de CI remoto: queda cubierto por AC06 de M0, en PASS y archivado el 2026-10-02 (ver desviación del 2026-10-02) |
| D03 | Modelo para agentes (M5/M6) | Interfaz `ModelProvider` con dos implementaciones: Ollama local como proveedor real y un LLM fake determinístico para tests. Ollama corre en un perfil opcional de Compose, con imagen fijada por digest, sólo red interna/loopback y un modelo pequeño descargado bajo demanda. Se llama por HTTP con httpx, sin SDKs de IA. Gates y tests pasan sin Ollama ni red. Prohibido llamar a proveedores de IA externos |
| D04 | Embeddings (M3) | Determinísticos y locales (hashing de n-gramas), sin descargas; FTS + vector + RRF reales en pgvector |
| D05 | Orquestación | Máquina de estados propia en Python; sin LangGraph |
| D06 | Persistencia | SQLAlchemy 2 Core + Alembic sobre psycopg 3 |
| D07 | Auth/RBAC | JWT firmado con claves locales de desarrollo, verificador compatible con OIDC, roles analista/supervisor/auditor, sólo loopback; segregación de funciones en la aprobación |
| D08 | Dashboard (M8) | Vite + React + TypeScript, CSS propio (sin Tailwind ni MUI), cliente generado desde OpenAPI, Vitest + Playwright |
| D09 | Observabilidad (M9) | SDK OpenTelemetry + Collector + Jaeger en perfil opcional de Compose; métricas en `/metrics` |
| D10 | Demo (M10) | Preparar walkthrough, dataset, reporte sanitizado y secret scan; no hacer público el repo ni desplegar. Superada el 2026-10-02 por decisión del propietario: repo público y demo estática en GitHub Pages, sin backend (ver Desviaciones) |
| D11 | Git | Una rama y un PR por hito. Se intenta `gh pr merge --auto --squash`. Como GitHub no ofrece auto-merge ni branch protection en repos privados del plan gratuito, el fallback es: evidencia del gate local y estado de AC en el PR, nota de CI remoto bloqueado por facturación y squash merge manual cuando pase el gate local; se borra la rama tras el merge |
| D12 | Dependencias | Autorizado instalar paquetes Python/npm fijados en lockfiles e imágenes Docker fijadas por digest |
| D13 | Bloqueos | Documentar, tomar la opción más conservadora y seguir con lo siguiente |

Restricciones vigentes: sólo datos sintéticos (sin PAN, CVV ni credenciales reales); ninguna ejecución financiera externa; aprobar no mueve dinero; los agentes no tienen permisos de resolución; puertos del host en el rango 181xx sólo en 127.0.0.1 (API 18180).

## Desviaciones

| Fecha | Decisión | Desviación y justificación |
|---|---|---|
| 2026-09-29 | D11 | `allow_auto_merge` no se puede activar: GitHub devuelve la función como no disponible para repos privados en plan gratuito. Se aplica el fallback previsto en D11 (merge manual por squash con evidencia del gate local) |
| 2026-10-01 | D11 | M2–M9 se integraron a `main` localmente con merge `--no-ff` (no squash) y sin PR: GitHub Actions está bloqueado por facturación y no se hizo push. Las ramas de hito se conservan para revisión; push, PRs y borrado de ramas quedan como decisión del usuario. No se reescribió historia: el mensaje equivocado del commit `df504d0` se corrigió con el commit vacío `7f04711` |
| 2026-10-01 | D05 | Hallazgo de M6: con el presupuesto por defecto (4 llamadas generativas), plan + borrador + revisión dejan sólo una llamada, y la reflexión (borrador + revisión) no cabe. Se registra como issue en el borrador en lugar de exceder el presupuesto |
| 2026-10-01 | D09 | La telemetría vive en `recon_store.telemetry` (paquete común a todos los procesos y necesario para el default `trace_context` del outbox) en vez de un paquete nuevo. La ruta de métricas genera el formato Prometheus sin dependencia adicional. El escaneo de secretos es un script propio (no gitleaks) para no descargar binarios de terceros |
| 2026-10-02 | D10, D11 | El propietario hizo público el repositorio (licencia MIT), habilitó GitHub Actions (gratis en repos públicos) y empujó `main`. El bloqueo de facturación ya no aplica. El run [36948716393](https://github.com/manuXD270516/fintech-ai-reconciliation-agent/actions/runs/36948716393) sobre `f92fe85` ejecutó el gate completo en verde. El run [36973958452](https://github.com/manuXD270516/fintech-ai-reconciliation-agent/actions/runs/36973958452), sobre la rama temporal `ci-intentional-contract-break` (`/health/live` devolviendo `ok`), quedó en rojo en pytest; la rama se borró. Con eso AC06 pasó a PASS y M0 se archivó. No hay despliegue |
| 2026-10-02 | D10, D09 | M11, por instrucción del propietario ("gitpages para los repos que podamos publicar"): el dashboard se publica en GitHub Pages en modo demo de sólo lectura, con un fixture sintético y sin backend. Además se agregan gitleaks, pip-audit, npm audit y Dependabot en un workflow `security` separado del gate offline, y se completan los drills pendientes de M9 (alertas en vivo y rollback con un `rules/v2` sintético). La historia con rutas locales no se reescribe |
