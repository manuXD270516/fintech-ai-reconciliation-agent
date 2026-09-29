# Decisiones de implementación M1–M10

Fecha: 2026-09-29. Decididas por el maintainer antes de la implementación autónoma de M1–M10. Cada change OpenSpec enlaza este archivo desde su `design.md` y cada PR incluye una checklist de cumplimiento. Una desviación sólo es válida si está registrada en la sección [Desviaciones](#desviaciones), eligiendo la opción más conservadora compatible con la decisión.

| # | Tema | Decisión |
|---|---|---|
| D01 | Alcance | M1→M6 (MVP técnico) con rigor completo, en orden de dependencias; si sobra tiempo, M7→M10 |
| D02 | OpenSpec | Un change por hito (proposal, specs con RF y escenarios, acceptance-criteria con Estado/Evidencia, design, tasks, test-strategy). Si todos sus AC pasan en local, se archiva y se promueve su spec sin preguntar. Los changes nuevos no incluyen AC de CI remoto: queda cubierto por AC06 de M0, PENDING por facturación de GitHub; M0 no se archiva |
| D03 | Modelo para agentes (M5/M6) | Interfaz `ModelProvider` con dos implementaciones: Ollama local como proveedor real y un LLM fake determinístico para tests. Ollama corre en un perfil opcional de Compose, con imagen fijada por digest, sólo red interna/loopback y un modelo pequeño descargado bajo demanda. Se llama por HTTP con httpx, sin SDKs de IA. Gates y tests pasan sin Ollama ni red. Prohibido llamar a proveedores de IA externos |
| D04 | Embeddings (M3) | Determinísticos y locales (hashing de n-gramas), sin descargas; FTS + vector + RRF reales en pgvector |
| D05 | Orquestación | Máquina de estados propia en Python; sin LangGraph |
| D06 | Persistencia | SQLAlchemy 2 Core + Alembic sobre psycopg 3 |
| D07 | Auth/RBAC | JWT firmado con claves locales de desarrollo, verificador compatible con OIDC, roles analista/supervisor/auditor, sólo loopback; segregación de funciones en la aprobación |
| D08 | Dashboard (M8) | Vite + React + TypeScript, CSS propio (sin Tailwind ni MUI), cliente generado desde OpenAPI, Vitest + Playwright |
| D09 | Observabilidad (M9) | SDK OpenTelemetry + Collector + Jaeger en perfil opcional de Compose; métricas en `/metrics` |
| D10 | Demo (M10) | Preparar walkthrough, dataset, reporte sanitizado y secret scan; no hacer público el repo ni desplegar |
| D11 | Git | Una rama y un PR por hito. Se intenta `gh pr merge --auto --squash`. Como GitHub no ofrece auto-merge ni branch protection en repos privados del plan gratuito, el fallback es: evidencia del gate local y estado de AC en el PR, nota de CI remoto bloqueado por facturación y squash merge manual cuando pase el gate local; se borra la rama tras el merge |
| D12 | Dependencias | Autorizado instalar paquetes Python/npm fijados en lockfiles e imágenes Docker fijadas por digest |
| D13 | Bloqueos | Documentar, tomar la opción más conservadora y seguir con lo siguiente |

Restricciones vigentes: sólo datos sintéticos (sin PAN, CVV ni credenciales reales); ninguna ejecución financiera externa; aprobar no mueve dinero; los agentes no tienen permisos de resolución; puertos del host en el rango 181xx sólo en 127.0.0.1 (API 18180).

## Desviaciones

| Fecha | Decisión | Desviación y justificación |
|---|---|---|
| 2026-09-29 | D11 | `allow_auto_merge` no se puede activar: GitHub devuelve la función como no disponible para repos privados en plan gratuito. Se aplica el fallback previsto en D11 (merge manual por squash con evidencia del gate local) |
