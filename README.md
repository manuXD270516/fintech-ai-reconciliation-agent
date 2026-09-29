# fintech-ai-reconciliation-agent

Diseño de una plataforma de conciliación de pagos: reglas determinísticas primero, investigación con IA sólo cuando aporta contexto y aprobación humana para decisiones operativas.

**Estado: sólo M0 (bootstrap técnico) implementado localmente.** Existen una API con endpoints de salud, PostgreSQL + pgvector y NATS JetStream en Docker Compose, y gates de calidad. **No hay** modelos de pagos, ingestion, conciliación, RAG, MCP, agentes, aprobación ni dashboard: siguen siendo diseño (M1–M10). El repositorio no está publicado; el workflow de CI existe, pero todavía no se ha ejecutado en GitHub.

## Qué incluye M0

| Ruta | Propósito |
|---|---|
| `GET /health/live` | Proceso vivo: `200 {"status":"alive","request_id":...}` |
| `GET /health/ready` | `200` si `database`, `vector` y `messaging` están `ok`; si no, `503` con cada estado (`ok`/`fail`/`timeout`) en ≤ 3 s |
| `GET /docs`, `GET /openapi.json` | Documentación técnica de la API |

No hay otras rutas; `tests/unit/test_scope.py` lo verifica. Readiness no escribe filas ni publica mensajes: hace `SELECT 1`, una distancia vectorial sobre literales y `account_info` de JetStream, en paralelo bajo un deadline global (`APP_READY_TIMEOUT_SECONDS`, por defecto 2.5, máximo 3). Las respuestas no incluyen hosts, URLs, SQL, trazas ni secretos. Cada respuesta lleva `X-Request-ID` (se acepta el del cliente si cumple `[A-Za-z0-9._-]{1,64}`; si no, se genera) y produce un log JSON con `request_id`, método, ruta sin query string, status y `duration_ms`.

## Prerrequisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| Docker Engine o Docker Desktop (contenedores Linux; WSL2 en Windows) con Compose v2 | Compose ≥ 2.24 (probado con Docker 29.8.0 y Compose 5.5.1, linux/amd64) | Stack local y smoke |
| [uv](https://docs.astral.sh/uv/) | exactamente 0.12.20 (`required-version` en `pyproject.toml`) | Instala CPython 3.12.14 y las dependencias bloqueadas; ejecuta el gate |
| Node.js + npm | 22.23.1 (`.nvmrc`) | OpenSpec 1.11.0 fijado en `package-lock.json` |
| git | cualquiera reciente | Clonar; el gate de política lista archivos con git |

No se requieren cuentas financieras ni claves de IA. El Python del sistema no se usa: uv descarga 3.12.14 (`.python-version`). `uv run python scripts/doctor.py` diagnostica cada prerrequisito y, si falta alguno, indica la acción para corregirlo.

## Guía desde un clone limpio

PowerShell (Windows):

```powershell
git clone <url> fintech-ai-reconciliation-agent; cd fintech-ai-reconciliation-agent
uv sync --locked                      # instala CPython 3.12.14 y las dependencias del lock
npm ci                                # OpenSpec 1.11.0 local
Copy-Item .env.example .env           # valores sintéticos, sólo locales
uv run python scripts/doctor.py       # prerrequisitos
uv run python scripts/gate.py static  # lint, tipos, tests, política, trazabilidad, OpenSpec, gate negativo
uv run python scripts/gate.py smoke   # Compose real: arranque, fallos, aislamiento, persistencia
```

bash (Linux/macOS): igual, con `cp .env.example .env`.

La API se publica en `127.0.0.1:18180` por defecto (no usa 8000 ni 5432, habitualmente ocupados por otros stacks locales). PostgreSQL y NATS no se publican en el host. Si 18180 está ocupado, cambia `API_HOST_PORT` en `.env`. Los valores de `.env.example` son marcadores `dev-only-*`, no secretos; `.env` está ignorado por git.

## Ciclo de vida local

```text
docker compose up -d --build     # postgres, db-init (one-shot), nats, api
curl http://127.0.0.1:18180/health/ready
docker compose stop              # detiene; conserva datos
docker compose start             # reanuda con los mismos volúmenes
docker compose down              # elimina contenedores; conserva volúmenes nombrados
```

**Reset destructivo (borra la base de datos y los streams JetStream locales):** `docker compose --profile smoke down --volumes`. No forma parte de ningún gate ni se ejecuta por defecto.

Aislamiento: sólo la API se publica, y únicamente en `127.0.0.1`. PostgreSQL y NATS están en una red Compose `internal` sin puertos publicados. `db-init` usa el superusuario de bootstrap para crear la extensión `vector` y el rol `recon_app` de forma idempotente. La API se conecta como `recon_app`, sin SUPERUSER, CREATEDB, CREATEROLE ni CREATE sobre la base o `public`. El contenedor de la API corre sin root, con filesystem de sólo lectura y sin capabilities.

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
| `smoke` | Compose real (ver [evidencia](openspec/changes/bootstrap-mvp-foundation/evidence/README.md)) |

## Versiones fijadas

| Componente | Versión / digest |
|---|---|
| PostgreSQL + pgvector | `pgvector/pgvector:0.8.6-pg17-trixie@sha256:724a4041afdb1750446e3f6b5cfa8f3b0ac5a2cf538ddfa6bfee4f94c2fa85c6` (PostgreSQL 17.11, vector 0.8.6) |
| NATS | `nats:2.14.7-alpine3.22@sha256:4063edae0717ba5f7501bfde75f97fd9b57f5b93597b92c70b6a6fbbf6a74e06` |
| Base de la API | `python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` |
| uv en la imagen | `ghcr.io/astral-sh/uv:0.12.20@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8` |
| Python (runtime) | fastapi 0.141.1, uvicorn 0.54.0, pydantic 2.13.5, pydantic-settings 2.15.0, psycopg[binary] 3.3.6, nats-py 2.16.0 (resto en `uv.lock`) |
| Python (dev) | ruff 0.16.9, mypy 2.3.1, pytest 9.1.1, pytest-asyncio 1.4.0, httpx 0.28.1 |
| OpenSpec | @fission-ai/openspec 1.11.0 |

Son las versiones verificadas juntas en este repositorio; no se afirma que sean las últimas.

## Estructura

```text
apps/api/        adaptador HTTP (FastAPI): sólo salud; Dockerfile (runtime + smoke)
infra/           init idempotente de PostgreSQL y configuración de NATS
scripts/         doctor, gate, smoke, trazabilidad, política, gate negativo
tests/unit       contratos sin infraestructura (inyección controlada de fallas)
tests/integration  ejecutados dentro de la red Compose contra servicios reales
openspec/        specs y change bootstrap-mvp-foundation (+ evidence/)
docs/            diseño M0–M10
```

`packages/domain` todavía no existe, a propósito. Cuando se cree en M1, contendrá reglas puras de dominio sin imports de HTTP, bus, base de datos ni LLM; `apps/api` sólo adaptará HTTP a esos casos de uso. M0 no crea clases de dominio vacías.

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

Todo objetivo de precisión, latencia o tokens de esos documentos es **EXPECTED**; nada se ha medido todavía. Los únicos datos **MEASURED** son los tiempos del smoke local de infraestructura de M0, con el alcance descrito en su evidencia; no son un benchmark.

## Change OpenSpec

[bootstrap-mvp-foundation](openspec/changes/bootstrap-mvp-foundation/proposal.md) especifica M0: [requirements](openspec/changes/bootstrap-mvp-foundation/specs/repository-foundation/spec.md), [acceptance criteria](openspec/changes/bootstrap-mvp-foundation/acceptance-criteria.md) (estado y evidencia de cada AC), [design](openspec/changes/bootstrap-mvp-foundation/design.md), [tasks](openspec/changes/bootstrap-mvp-foundation/tasks.md) y [test strategy](openspec/changes/bootstrap-mvp-foundation/test-strategy.md). El change no está archivado y `openspec/specs/` sigue vacío hasta decidir su integración.

## Límites de la demostración

Datos y proveedores sintéticos. Sin PAN, CVV, credenciales reales, dinero real ni ejecución de reembolsos o ajustes contables. El sistema conserva observaciones y evidencia; no sustituye al ledger ni al procesador de pagos. Toda decisión operativa exige una identidad humana autorizada, incluso si la IA expresa alta confianza. M0 no tiene autenticación de usuarios: sólo es apto para uso local en loopback, nunca para despliegue público.
