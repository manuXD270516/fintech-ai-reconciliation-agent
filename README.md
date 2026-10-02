# fintech-ai-reconciliation-agent

Diseño de una plataforma de conciliación de pagos: reglas determinísticas primero, investigación con IA sólo cuando aporta contexto y aprobación humana para decisiones operativas.

**Estado: M0 (bootstrap), M1 (dominio transaccional), M2 (conciliación determinística), M3 (knowledge base híbrida), M4 (servidor MCP de sólo lectura), M5 (investigación acotada), M6 (revisión y aprobación humana; cierre del MVP técnico), M7 (framework de evaluación), M8 (dashboard de investigación), M9 (observabilidad y seguridad) y M10 (demo reproducible, sin publicar) implementados y verificados localmente. No está listo para producción.** Recorrido de la demo: [docs/demo/walkthrough.md](docs/demo/walkthrough.md); resultados y límites: [docs/demo/results.md](docs/demo/results.md). Existen PostgreSQL + pgvector y NATS JetStream en Docker Compose, el dominio puro (`packages/domain`), su persistencia (`packages/store`), ingestion sintética por HTTP y eventos con cuarentena, el motor de reglas `rules/v1`, runs versionados, un worker con outbox/inbox y dead letters, una API `/v1` autenticada con JWT de desarrollo, una base de conocimiento sintética con retrieval híbrido (FTS + vector + RRF) y abstención (`packages/knowledge`), `fintech-mcp-server` (`apps/mcp-server`), un proceso MCP con seis tools de sólo lectura, y un agente de investigación acotado (`packages/agents`, proceso `investigator`) que produce borradores sin efecto operativo. Los tests y la demo usan un proveedor de modelo **scripted determinístico** (resultados etiquetados SIMULATED); Ollama local es opcional y está apagado por defecto; no se llama a ningún proveedor de IA externo. Un revisor independiente evalúa cada borrador y las decisiones operativas son comandos humanos versionados, idempotentes y auditados (aprobar sólo registra la decisión; nunca mueve dinero). Decisiones de implementación: [docs/11-implementation-decisions.md](docs/11-implementation-decisions.md). Remoto: [manuXD270516/fintech-ai-reconciliation-agent](https://github.com/manuXD270516/fintech-ai-reconciliation-agent) (público, licencia MIT). GitHub Actions ejecuta el mismo gate (`scripts/gate.py`, 12 pasos, smoke Compose incluido) en cada push a `main`. El run [36948716393](https://github.com/manuXD270516/fintech-ai-reconciliation-agent/actions/runs/36948716393), sobre `f92fe85`, pasó completo con smoke 24/24. El run [36973958452](https://github.com/manuXD270516/fintech-ai-reconciliation-agent/actions/runs/36973958452) demostró que el CI rechaza un contrato roto, sobre una rama temporal ya borrada. Los changes M0–M10 están archivados.

## Qué incluye M0

| Ruta | Propósito |
|---|---|
| `GET /health/live` | Proceso vivo: `200 {"status":"alive","request_id":...}` |
| `GET /health/ready` | `200` si `database`, `vector` y `messaging` están `ok`; si no, `503` con cada estado (`ok`/`fail`/`timeout`) en ≤ 3 s |
| `GET /docs`, `GET /openapi.json` | Documentación técnica de la API |

## Qué agrega M2

| Ruta (todas exigen `Authorization: Bearer <JWT>`) | Rol | Propósito |
|---|---|---|
| `POST /v1/artifacts` | `integration` | CSV sintético con clave de idempotencia → recibo con aceptadas, duplicadas, conflictos y cuarentena por fila |
| `POST /v1/batches`, `GET /v1/batches/{id}` | `analyst` / lectura | Lote con ventana `[inicio, fin)`, zona horaria, par de fuentes y cutoff |
| `POST /v1/batches/{id}/sources/{source}/complete` | `integration` | Marca explícita de completitud de una fuente |
| `POST /v1/batches/{id}/runs` | `analyst` | Solicita un run (202); el worker lo ejecuta vía outbox → JetStream |
| `GET /v1/runs/{id}`, `GET /v1/runs/{id}/results` | `analyst`/`supervisor`/`auditor` | Estado, snapshot hash, conteos y resultados paginados |

El tenant sale siempre del token. Las fuentes también pueden llegar como eventos JetStream en `recon.ingest.<tenant>.<source>.<provider>` (un evento = un artefacto de una fila, idempotente por `event_id`); los mensajes malformados van a `recon.dlq.<consumer>`. Tokens locales: `uv run python scripts/dev_auth.py init` y `uv run python scripts/dev_auth.py token --sub ana --role analyst` (claves en `.dev-keys/`, ignorado por git; sólo el JWKS público entra al contenedor).

El motor `rules/v1` es puro y no importa clientes de modelos ni HTTP: EXACT exige referencia fuerte única, dinero idéntico y estado igual; diferencias con referencia compartida quedan `UNMATCHED` con discrepancias enlazadas; los candidatos débiles reciben un score de ranking (no una probabilidad) y los empates se conservan; los faltantes son `WAITING_SOURCE` hasta el cutoff y la completitud. Evidencia: [deterministic-reconciliation](openspec/changes/archive/2026-10-01-deterministic-reconciliation/evidence/README.md).

## Qué agrega M3

Una base de conocimiento sintética (`datasets/synthetic/knowledge-v1`: 17 documentos ES/EN versionados de dos proveedores ficticios y 38 queries etiquetadas) que el job one-shot `knowledge-ingest` publica en PostgreSQL de forma atómica e idempotente. `recon_knowledge` fragmenta por secciones, calcula embeddings locales de hashing (256 dims, **no semánticos**, sin descargas) y recupera combinando FTS por idioma, lookup exacto de códigos de error y búsqueda vectorial exacta en pgvector, fusionados con RRF (k=60). Todas las ramas aplican los mismos filtros duros (tenant, ACL, publicado, vigencia y `as_of`); si no hay evidencia suficiente, abstiene con un motivo; el contenido con instrucciones al modelo vuelve marcado como no confiable. `python -m recon_knowledge evaluate` mide baselines lexical/vector/híbrido (MEASURED, corpus sintético, umbral ajustado sólo en `dev`): ver [evidencia de M3](openspec/changes/archive/2026-10-01-hybrid-knowledge-retrieval/evidence/README.md). No hay rutas HTTP nuevas: el conocimiento se expone por MCP (M4).

## Qué agrega M4

`fintech-mcp-server` (SDK oficial `mcp==2.2.0`, revisión de protocolo `2025-11-25`, transporte stdio) expone exactamente `get_transaction`, `find_related_transactions`, `get_reconciliation_batch`, `get_provider_status`, `search_incidents` y `search_provider_docs`, con JSON Schema de entrada/salida cerrados, procedencia por resultado, errores estructurados (`NOT_FOUND`, `FORBIDDEN`, `STALE_SNAPSHOT`, `TIMEOUT`…), timeouts, límite de 64 KiB, rate limit, dos llamadas concurrentes y cursores firmados. Sujeto, tenant y scopes vienen del entorno del proceso, nunca de los argumentos; recursos de otro tenant son indistinguibles de inexistentes. Se conecta con el rol `recon_mcp`, que sólo lee tablas de evidencia e inserta auditoría (cada llamada queda auditada con hash de argumentos). No existen write tools. Ejecución local: `MCP_SUBJECT=... MCP_TENANT_ID=... MCP_SCOPES=... python -m recon_mcp --backend sql` (o `--backend fixture` con `MCP_FIXTURE` para pruebas de contrato). Evidencia: [read-only-mcp](openspec/changes/archive/2026-10-01-read-only-mcp/evidence/README.md).

## Qué agrega M5

| Ruta | Rol | Propósito |
|---|---|---|
| `POST /v1/runs/{run_id}/results/{ordinal}/investigations` | `analyst` | Solicita una investigación (202); repetirla sin evidencia nueva devuelve la misma (200) |
| `GET /v1/investigations/{id}` | `analyst`/`supervisor`/`auditor` | Estado, plan, pasos, uso de presupuesto y borrador |

El proceso `investigator` consume `InvestigationRequested`, toma la investigación con un claim atómico y ejecuta una máquina de estados persistida: routing determinístico (exactos, espera y faltantes no llaman al modelo), plan por plantilla más pasos propuestos por el modelo que pasan una política (sólo tools de lectura, IDs y proveedor del caso, máximo 6 llamadas), evidencia obtenida únicamente por `fintech-mcp-server` (stdio, rol `recon_mcp`) y una fase de evidencia determinística que descarta afirmaciones sin cita resoluble o FACTs sin registro que los respalde. El borrador separa FACT/INFERENCE/HYPOTHESIS, declara la confianza como `uncalibrated` y tiene `operational_effect: none`. Presupuesto por investigación: 6 llamadas MCP, 4 generativas, 16 000 tokens, 60 s. `RECON_MODEL_PROVIDER=ollama` y `docker compose --profile ollama up -d ollama` activan un modelo local real (no usado en gates). Evidencia: [bounded-investigation](openspec/changes/archive/2026-10-01-bounded-investigation/evidence/README.md).

## Qué agrega M6

| Ruta | Rol | Propósito |
|---|---|---|
| `POST /v1/runs/{run_id}/results/{ordinal}/cases` | `analyst` | Abre (idempotente) el caso de un resultado |
| `GET /v1/cases/{id}` | lectura | Caso, versión, recomendaciones, decisiones y si su run sigue siendo el más reciente |
| `POST /v1/cases/{id}/recommendations` | `analyst` | Propone una acción no operativa; adoptar un borrador exige revisión `SUPPORTED` |
| `POST /v1/cases/{id}/decisions` | `supervisor` | Aprueba/rechaza/pide información con `expected_version`, motivo e `idempotency_key` |
| `POST /v1/cases/{id}/close` | `supervisor` | Cierre humano con motivo |
| `GET /v1/cases/{id}/audit` | `auditor`/`supervisor` | Traza reconstruida: run y reglas, recomendaciones, decisiones, investigación (pasos MCP, citas, revisión) y auditoría |

Antes de que una persona vea un borrador, un revisor aplica chequeos determinísticos y una revisión del modelo aislada (sólo caso, afirmaciones y citas); gana el resultado más conservador y hay como máximo una reflexión si cabe en el presupuesto. Una decisión se rechaza si quien decide propuso la recomendación o pidió la investigación (segregación de funciones), si la versión no es la vigente, si la recomendación expiró o si llegó un run más nuevo del lote (la recomendación queda obsoleta). Decisiones concurrentes producen una sola transición; repetir la clave de idempotencia devuelve la decisión original. Decisión, estado, auditoría y evento `ApprovalRecorded` se confirman juntos; los intentos rechazados también se auditan. Evidencia: [review-and-human-approval](openspec/changes/archive/2026-10-01-review-and-human-approval/evidence/README.md).

## Qué agrega M7

`python -m recon_evals run --suite all|<suite>` ejecuta suites descritas por manifests versionados (`evals/src/recon_evals/manifests/`) y escribe un reporte JSON + Markdown con commit, estado del árbol, host, hashes de datasets, métricas con n e intervalos de Wilson, gates y fallos. Cada resultado se etiqueta MEASURED (componente real sobre datos sintéticos), SIMULATED (salida del modelo scripted) o SKIPPED (falta una dependencia); los umbrales de docs/07 son EXPECTED y sólo aparecen como gates.

| Suite | Etiqueta | Qué mide |
|---|---|---|
| `reconciliation` | MEASURED | 1210 pagos sintéticos en 121 familias (split 60/20/20 por familia): accuracy, precision/recall de EXACT, falsos EXACT, F1 por clase y de discrepancias |
| `retrieval` | MEASURED (sólo con PostgreSQL) | Baselines lexical/vector/híbrido de M3 por split, violaciones de ACL |
| `tools` | MEASURED | Contratos de `fintech-mcp-server` en una sesión MCP real en memoria |
| `investigation` | SIMULATED | 8 escenarios adversariales × 3: tools prohibidas, hechos sin soporte, presupuestos, completitud |
| `approval` | MEASURED | 576 intentos de decisión contra un oráculo independiente |

El paso `evals` del gate (también en CI) corre las suites offline y falla si un gate crítico falla o si una métrica empeora frente a `evals/baselines/offline.json`; `retrieval` corre en el smoke. Evidencia: [evaluation-framework](openspec/changes/archive/2026-10-01-evaluation-framework/evidence/README.md).

## Qué agrega M8

| Ruta | Rol | Propósito |
|---|---|---|
| `GET /v1/batches` | lectura | Lotes recientes del tenant |
| `GET /v1/batches/{id}/runs` | lectura | Runs de un lote (el más reciente primero) |
| `GET /v1/cases?status=` | lectura | Cola de casos, filtrable por estado |

`apps/web` es un dashboard (Vite + React + TypeScript, CSS propio) servido en `127.0.0.1:18181` con proxy de `/api` a la API, sin CORS. Su cliente se genera desde OpenAPI (`scripts/export_openapi.py` → `apps/web/openapi.json` → `openapi-typescript`), y un test falla ante drift. Recorre lotes, runs y resultados; muestra la investigación con timeline y un borrador que separa hechos, inferencias e hipótesis con citas, revisión, confianza `uncalibrated` y etiqueta SIMULATED; y abre casos donde el analista propone y el supervisor decide sobre la versión vigente con el efecto exacto a la vista (registrar la decisión, nunca mover dinero), sin aprobación masiva y con el formulario deshabilitado si el caso quedó obsoleto. Los errores de la API se traducen por código y la autorización es siempre de la API. La sesión es un JWT de desarrollo pegado en la pantalla de ingreso (`scripts/dev_auth.py token ...`), no apta para producción.

```text
npm ci --prefix apps/web
npx --prefix apps/web playwright install chromium   # una vez, para el E2E
npm --prefix apps/web run dev                         # http://127.0.0.1:18181 con el stack arriba
```

El paso `web` del gate verifica tipos generados, `tsc`, Vitest y build; el smoke (`M8-T07`) ejecuta un E2E Playwright analista → supervisor → auditor contra el stack real, con pasos por teclado y axe (WCAG 2 A/AA) sin violaciones serias ni críticas. Evidencia: [investigation-dashboard](openspec/changes/archive/2026-10-01-investigation-dashboard/evidence/README.md).

## Qué agrega M9

- **Trazas OpenTelemetry opcionales.** Se apagan por defecto. Con `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 docker compose --profile observability up -d`, una investigación produce una sola traza: API → outbox → NATS → worker → investigador → `fintech-mcp-server`. Se ve en Jaeger (`http://127.0.0.1:18186`). `uv run python scripts/observability_demo.py` lo verifica y vuelve a apagarlo. Los spans no llevan tenant, sujeto ni montos.
- **`GET /metrics`** (Prometheus, sin autenticación, sólo loopback). Expone:
  - contadores e histogramas HTTP por plantilla de ruta;
  - outbox pendiente y su antigüedad;
  - latidos de worker e investigador;
  - runs, resultados, investigaciones (presupuesto y tokens), revisiones y cola humana;
  - rechazos de decisión y llamadas MCP en la última hora;
  - dead letters sin triar.

  Sólo agregados de baja cardinalidad, sin IDs ni tenants.
- **Alertas EXPECTED** en `infra/observability/alerts.toml`, evaluadas con `uv run python scripts/ops.py alerts`. Cada una enlaza un runbook de [docs/runbooks](docs/runbooks/README.md).
- **Operación auditada:**
  - triage de dead letters (`docker compose exec worker python -m recon_worker.dlq list|triage`);
  - revocación de documentos (`python -m recon_knowledge revoke`);
  - backup y chequeo de restore sobre una base temporal (`scripts/ops.py backup|restore-check`).
- **Drills en el smoke:**
  - `M9-T04`: métricas sanas.
  - `M9-T05`: caída de NATS y worker, con alertas que disparan y se limpian, y el run completado una sola vez; dead letters con replay idempotente.
  - `M9-T06`: backup y restore con conteos y digest del audit trail.
- **Seguridad:**
  - matriz ruta × rol verificada por test;
  - paso de gate `secrets` (escaneo heurístico de toda la historia git);
  - [revisión de seguridad](docs/security-review.md) con hallazgos abiertos (por ejemplo, `/metrics` sin autenticación, no apto para publicarse).

Evidencia: [observability-security](openspec/changes/archive/2026-10-01-observability-security/evidence/README.md).

## Qué agrega M10

- **Sesiones de demo aisladas.** `uv run python scripts/demo.py seed` crea un tenant `demo-<id>`, ingiere el dataset sintético por la API, ejecuta los 12 lotes y verifica los resultados contra las etiquetas. Los tokens de la sesión quedan en `.demo/`, que git ignora.
- **Kill switch de IA.** Con `APP_AI_ENABLED=false` (o `scripts/demo.py kill-switch off`), las investigaciones nuevas responden 503 `ai_disabled`. La conciliación, los casos, las propuestas sin borrador y las decisiones siguen funcionando. `/metrics` lo expone como `recon_ai_enabled`.
- **Documentación de la demo:**
  - [Walkthrough](docs/demo/walkthrough.md), reproducible desde un clone limpio.
  - [Resultados sanitizados](docs/demo/results.md), con etiquetas MEASURED/SIMULATED/EXPECTED, costos, límites y decisiones pendientes del propietario.
  - [Ficha de datasets](datasets/README.md).
- **Revisión previa a publicar:**
  - Inventario de licencias de terceros (`scripts/license_inventory.py`).
  - Rutas de perfil de usuario prohibidas en el árbol (paso `policy`).
  - Escaneo de secretos de toda la historia.
- **Smoke `M10-T03`:** verifica el aislamiento entre sesiones y el flujo humano completo con la IA apagada.

M10 no publicó ni desplegó nada. Después, el propietario hizo público el repositorio con licencia MIT y habilitó el CI. Nada se despliega. Siguen abiertas:
- la historia git con rutas locales en logs antiguos;
- un escáner externo de secretos.

Evidencia: [public-demo](openspec/changes/archive/2026-10-01-public-demo/evidence/README.md).

No hay otras rutas (además de `/metrics`, M9); `tests/unit/test_scope.py` verifica el catálogo exacto y `tests/unit/test_access_matrix.py` los roles de cada ruta. Readiness no escribe filas ni publica mensajes: hace `SELECT 1`, una distancia vectorial sobre literales y `account_info` de JetStream, en paralelo bajo un deadline global (`APP_READY_TIMEOUT_SECONDS`, por defecto 2.5, máximo 3). Las respuestas no incluyen hosts, URLs, SQL, trazas ni secretos. Cada respuesta lleva `X-Request-ID` (se acepta el del cliente si cumple `[A-Za-z0-9._-]{1,64}`; si no, se genera) y produce un log JSON con `request_id`, método, ruta sin query string, status y `duration_ms`.

## Prerrequisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| Docker Engine o Docker Desktop (contenedores Linux; WSL2 en Windows) con Compose v2 | Compose ≥ 2.24 (probado con Docker 29.8.0 y Compose 5.5.1, linux/amd64) | Stack local y smoke |
| [uv](https://docs.astral.sh/uv/) | exactamente 0.12.20 (`required-version` en `pyproject.toml`) | Instala CPython 3.12.14 y las dependencias bloqueadas; ejecuta el gate |
| Node.js + npm | 22.23.1 (`.nvmrc`) | OpenSpec 1.11.0 fijado en `package-lock.json`; dashboard `apps/web` (M8) |
| Chromium de Playwright | el de Playwright 1.63.0 (`npx --prefix apps/web playwright install chromium`) | E2E del dashboard en el smoke |
| git | cualquiera reciente | Clonar; el gate de política lista archivos con git |

No se requieren cuentas financieras ni claves de IA. El Python del sistema no se usa: uv descarga 3.12.14 (`.python-version`). `uv run python scripts/doctor.py` diagnostica cada prerrequisito y, si falta alguno, indica la acción para corregirlo.

## Guía desde un clone limpio

PowerShell (Windows):

```powershell
git clone https://github.com/manuXD270516/fintech-ai-reconciliation-agent.git
cd fintech-ai-reconciliation-agent
uv sync --locked                      # instala CPython 3.12.14 y las dependencias del lock
npm ci                                # OpenSpec 1.11.0 local
npm ci --prefix apps/web              # dashboard (M8)
npx --prefix apps/web playwright install chromium
Copy-Item .env.example .env           # valores sintéticos, sólo locales
uv run python scripts/doctor.py       # prerrequisitos
uv run python scripts/gate.py static  # lint, tipos, tests, política, trazabilidad, OpenSpec, gate negativo
uv run python scripts/gate.py smoke   # Compose real: arranque, fallos, aislamiento, persistencia
```

bash (Linux/macOS): igual, con `cp .env.example .env`.

La API se publica en `127.0.0.1:18180` por defecto (no usa 8000 ni 5432, habitualmente ocupados por otros stacks locales). PostgreSQL y NATS no se publican en el host. Si 18180 está ocupado, cambia `API_HOST_PORT` en `.env`. Los valores de `.env.example` son marcadores `dev-only-*`, no secretos; `.env` está ignorado por git.

## Ciclo de vida local

```text
uv run python scripts/dev_auth.py init   # una vez: claves RS256 locales (la API no arranca sin JWKS)
docker compose up -d --build     # postgres, db-init y migrate (one-shot), nats, api, worker
curl http://127.0.0.1:18180/health/ready
docker compose stop              # detiene; conserva datos
docker compose start             # reanuda con los mismos volúmenes
docker compose down              # elimina contenedores; conserva volúmenes nombrados
```

**Reset destructivo (borra la base de datos y los streams JetStream locales):** `docker compose --profile smoke down --volumes`. No forma parte de ningún gate ni se ejecuta por defecto.

Aislamiento: sólo la API se publica, y únicamente en `127.0.0.1`. PostgreSQL y NATS están en una red Compose `internal` sin puertos publicados. `db-init` usa el superusuario de bootstrap para crear la extensión `vector` y el rol `recon_app` de forma idempotente. La API se conecta como `recon_app`, sin SUPERUSER, CREATEDB, CREATEROLE ni CREATE sobre la base o `public`. El contenedor de la API corre sin root, con filesystem de sólo lectura y sin capabilities. El job `migrate` aplica las migraciones Alembic del esquema `recon` con el rol de bootstrap y concede a `recon_app` sólo `SELECT, INSERT` sobre observaciones y auditoría (historia append-only).

Configuración: la API lee `APP_*`. Si un valor obligatorio falta o es inválido, el proceso termina con código 2 y una línea JSON que nombra cada campo (`APP_DB_PASSWORD`, `APP_NATS_URL`, …) sin mostrar su valor. `APP_NATS_URL` no admite credenciales embebidas.

## Gate de calidad

`scripts/gate.py` es el único punto de entrada; CI (`.github/workflows/ci.yml`) ejecuta los mismos pasos en el mismo orden. El gate elimina del entorno las variables de credenciales de IA y falla con código distinto de cero si falla cualquier paso.

| Paso | Qué verifica |
|---|---|
| `lock` | `uv lock --check` |
| `lint` | Ruff check + format |
| `types` | mypy estricto (API, scripts, tests) |
| `test` | pytest: contratos de salud y degradación, deadline, configuración, request ID/redacción, rutas, trazabilidad, doctor, paridad CI |
| `policy` | Sin dependencias IA/LLM en lockfiles; `.env` ignorado; escaneo heurístico de claves y PAN (Luhn) |
| `trace` | Seis artefactos por change; AC → RF/T/tasks existentes y cubiertos; PASS exige evidencia; tareas marcadas exigen AC en PASS |
| `openspec` | `openspec validate --all --strict --no-interactive` |
| `negative` | En copias temporales, cada defecto inyectado (spec, trazabilidad, contrato, ruta extra) debe romper su paso; el árbol real no cambia |
| `evals` | Suites offline de `recon_evals`: gates críticos y regresiones frente al baseline (M7) |
| `web` | Dashboard: tipos generados al día con `openapi.json`, `tsc`, Vitest y build de producción (M8) |
| `secrets` | Escaneo heurístico de secretos, PAN (Luhn) y rutas prohibidas en toda la historia git (M9; no reemplaza a gitleaks) |
| `smoke` | Compose real (ver [evidencia](openspec/changes/archive/2026-10-02-bootstrap-mvp-foundation/evidence/README.md)) |

## Versiones fijadas

| Componente | Versión / digest |
|---|---|
| PostgreSQL + pgvector | `pgvector/pgvector:0.8.6-pg17-trixie@sha256:724a4041afdb1750446e3f6b5cfa8f3b0ac5a2cf538ddfa6bfee4f94c2fa85c6` (PostgreSQL 17.11, vector 0.8.6) |
| NATS | `nats:2.14.7-alpine3.22@sha256:4063edae0717ba5f7501bfde75f97fd9b57f5b93597b92c70b6a6fbbf6a74e06` |
| Base de la API | `python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` |
| uv en la imagen | `ghcr.io/astral-sh/uv:0.12.20@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8` |
| Python (runtime) | fastapi 0.141.1, uvicorn 0.54.0, pydantic 2.13.5, pydantic-settings 2.15.0, psycopg[binary] 3.3.6, nats-py 2.16.0 (resto en `uv.lock`) |
| Python (persistencia, M1) | sqlalchemy 2.1.1, alembic 1.20.0, tzdata 2026.4 |
| Python (auth, M2) | pyjwt[crypto] 2.15.1, cryptography 50.0.1 |
| Python (dev) | ruff 0.16.9, mypy 2.3.1, pytest 9.1.1, pytest-asyncio 1.4.0, httpx 0.28.1, hypothesis 6.168.3 |
| OpenSpec | @fission-ai/openspec 1.11.0 |
| Observabilidad (M9, opcional) | opentelemetry-sdk y opentelemetry-exporter-otlp-proto-http 1.45.0; `otel/opentelemetry-collector:0.162.0@sha256:310a800a…`, `jaegertracing/jaeger:2.21.0@sha256:3d0ac795…` (digests completos en `compose.yaml`) |
| Dashboard (M8) | vite 8.3.1, react 19.3.0, typescript 5.9.3, openapi-typescript 7.13.0, openapi-fetch 0.17.0, vitest 5.0.3, @playwright/test 1.63.0, @axe-core/playwright 4.13.0 (resto en `apps/web/package-lock.json`) |

Son las versiones verificadas juntas en este repositorio; no se afirma que sean las últimas.

## Estructura

```text
apps/api/          adaptador HTTP (FastAPI): salud y /v1 con JWT/RBAC; Dockerfile (runtime + smoke)
apps/worker/       relay de outbox, consumidores JetStream (runs, ingestion por eventos) y DLQ
apps/mcp-server/   fintech-mcp-server: seis tools MCP de sólo lectura (M4)
apps/investigator/ proceso de investigación: consume eventos y ejecuta el agente acotado (M5)
apps/web/          dashboard de investigación y aprobación (Vite + React + TS), Vitest y Playwright (M8)
packages/agents/   routing, plan, cliente MCP, fase de evidencia, proveedores scripted/Ollama (M5)
packages/domain/   dominio puro: Money, observaciones, revisiones, lotes, ingestion, reglas rules/v1
packages/store/    SQLAlchemy Core + migraciones Alembic; ingesta atómica, runs, outbox/inbox
packages/knowledge/ corpus, chunking, embeddings locales, retrieval híbrido y evaluación (M3)
datasets/          datasets sintéticos versionados con manifest (scripts/generate_synthetic.py)
infra/             init idempotente de PostgreSQL, configuración de NATS, Collector y alertas (M9)
scripts/           doctor, gate, smoke, trazabilidad, política, gate negativo
tests/unit         contratos y propiedades sin infraestructura
tests/integration  ejecutados dentro de la red Compose contra servicios reales
openspec/          specs vigentes, changes activos y archivados (+ evidence/)
docs/              diseño M0–M10, decisiones de implementación, runbooks y revisión de seguridad
```

`packages/domain` no importa HTTP, bus, base de datos ni LLM (un test AST lo verifica); `packages/store` depende del dominio, nunca al revés.

## Documentación de diseño

| Entregable | Documento |
|---|---|
| 1. Domain analysis | [Dominio e invariantes](docs/01-domain.md#dominio) |
| 2. Bounded contexts | [Límites y propiedad de datos](docs/01-domain.md#bounded-contexts) |
| 3. Actors | [Actores y permisos](docs/01-domain.md#actores) |
| 4. Principal use cases | [Casos de uso](docs/01-domain.md#casos-de-uso) |
| 5. Architecture proposal; NestJS vs FastAPI | [Arquitectura y decisiones](docs/02-architecture.md) |
| 6. C4 context | [Contexto C4](docs/03-c4.md#c4-context) |
| 7. C4 container model | [Contenedores C4](docs/03-c4.md#c4-container-model) |
| 8. Agent responsibilities | [Investigación y revisión humana](docs/04-agents.md) |
| 9. MCP design | [fintech-mcp-server](docs/05-mcp.md) |
| 10. RAG design | [Knowledge base híbrida](docs/06-rag.md) |
| 11. Eval strategy | [Datasets, métricas y gates](docs/07-evals.md) |
| 12. Risk analysis | [Riesgos, seguridad y observabilidad](docs/08-risks.md) |
| 13. Milestone roadmap | [M0–M10](docs/09-roadmap.md) |

Todo objetivo de precisión, latencia o tokens de esos documentos es **EXPECTED**. Lo **MEASURED** se limita a los reportes de `recon_evals` y del smoke sobre datos sintéticos, con el alcance descrito en cada evidencia (por ejemplo, el retrieval híbrido de M3 no alcanza varios objetivos EXPECTED); no son benchmarks ni prueban generalización a datos reales. Las salidas del modelo en tests y demo son **SIMULATED** (proveedor scripted).

## Change OpenSpec

[bootstrap-mvp-foundation](openspec/changes/archive/2026-10-02-bootstrap-mvp-foundation/proposal.md) especifica M0: [requirements](openspec/changes/archive/2026-10-02-bootstrap-mvp-foundation/specs/repository-foundation/spec.md), [acceptance criteria](openspec/changes/archive/2026-10-02-bootstrap-mvp-foundation/acceptance-criteria.md) (estado y evidencia de cada AC), [design](openspec/changes/archive/2026-10-02-bootstrap-mvp-foundation/design.md), [tasks](openspec/changes/archive/2026-10-02-bootstrap-mvp-foundation/tasks.md) y [test strategy](openspec/changes/archive/2026-10-02-bootstrap-mvp-foundation/test-strategy.md). Está archivado desde el 2026-10-02 con AC01–AC08 en PASS: el CI remoto pasó en verde (run 36948716393) y rechazó una ruptura intencional de contrato en una rama temporal (run [36973958452](https://github.com/manuXD270516/fintech-ai-reconciliation-agent/actions/runs/36973958452)).

[deterministic-reconciliation](openspec/changes/archive/2026-10-01-deterministic-reconciliation/proposal.md) (M2) está archivado con AC01–AC11 en PASS; su spec vigente es [openspec/specs/deterministic-reconciliation](openspec/specs/deterministic-reconciliation/spec.md).

M3–M10 siguen el mismo patrón (change archivado con sus AC en PASS y evidencia, spec vigente en `openspec/specs/`): `hybrid-knowledge-retrieval`, `read-only-mcp`, `bounded-investigation`, `review-and-human-approval`, `evaluation-framework`, `investigation-dashboard`, `observability-security` y `public-demo`; los enlaces a cada evidencia están en las secciones "Qué agrega" de arriba.

[transaction-domain](openspec/changes/archive/2026-09-29-transaction-domain/proposal.md) (M1) está archivado con AC01–AC09 en PASS ([evidencia](openspec/changes/archive/2026-09-29-transaction-domain/evidence/README.md)); su spec vigente es [openspec/specs/transaction-domain](openspec/specs/transaction-domain/spec.md).

## Límites de la demostración

Datos y proveedores sintéticos. Sin PAN, CVV, credenciales reales, dinero real ni ejecución de reembolsos o ajustes contables. El sistema conserva observaciones y evidencia; no sustituye al ledger ni al procesador de pagos. Toda decisión operativa exige una identidad humana autorizada, incluso si la IA expresa alta confianza. La autenticación usa JWT firmados con claves locales de desarrollo, sin IdP real: sólo es apto para uso local en loopback, nunca para despliegue público.
