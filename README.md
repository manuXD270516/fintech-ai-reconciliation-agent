# fintech-ai-reconciliation-agent

Diseño de una plataforma de conciliación de pagos: reglas determinísticas primero, investigación con IA sólo cuando aporta contexto y aprobación humana para decisiones operativas.

**Estado: M0 (bootstrap), M1 (dominio transaccional), M2 (conciliación determinística) y M3 (knowledge base híbrida) implementados y verificados localmente.** Existen PostgreSQL + pgvector y NATS JetStream en Docker Compose, el dominio puro (`packages/domain`), su persistencia (`packages/store`), ingestion sintética por HTTP y eventos con cuarentena, el motor de reglas `rules/v1`, runs versionados, un worker con outbox/inbox y dead letters, una API `/v1` autenticada con JWT de desarrollo y una base de conocimiento sintética con retrieval híbrido (FTS + vector + RRF) y abstención (`packages/knowledge`). **No hay** MCP, agentes, aprobación ni dashboard: siguen siendo diseño (M4–M10). Decisiones de implementación: [docs/11-implementation-decisions.md](docs/11-implementation-decisions.md). Remoto: [manuXD270516/fintech-ai-reconciliation-agent](https://github.com/manuXD270516/fintech-ai-reconciliation-agent) (privado). El workflow de CI está en el repo; GitHub no ha llegado a ejecutar jobs porque la cuenta tiene un bloqueo de facturación/límite de gasto.

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

Una base de conocimiento sintética (`datasets/synthetic/knowledge-v1`: 17 documentos ES/EN versionados de dos proveedores ficticios y 38 queries etiquetadas) que el job one-shot `knowledge-ingest` publica en PostgreSQL de forma atómica e idempotente. `recon_knowledge` fragmenta por secciones, calcula embeddings locales de hashing (256 dims, **no semánticos**, sin descargas) y recupera combinando FTS por idioma, lookup exacto de códigos de error y búsqueda vectorial exacta en pgvector, fusionados con RRF (k=60). Todas las ramas aplican los mismos filtros duros (tenant, ACL, publicado, vigencia y `as_of`); si no hay evidencia suficiente, abstiene con un motivo; el contenido con instrucciones al modelo vuelve marcado como no confiable. `python -m recon_knowledge evaluate` mide baselines lexical/vector/híbrido (MEASURED, corpus sintético, umbral ajustado sólo en `dev`): ver [evidencia de M3](openspec/changes/archive/2026-10-01-hybrid-knowledge-retrieval/evidence/README.md). No hay rutas HTTP nuevas: el conocimiento se expondrá por MCP en M4.

No hay otras rutas; `tests/unit/test_scope.py` verifica el catálogo exacto. Readiness no escribe filas ni publica mensajes: hace `SELECT 1`, una distancia vectorial sobre literales y `account_info` de JetStream, en paralelo bajo un deadline global (`APP_READY_TIMEOUT_SECONDS`, por defecto 2.5, máximo 3). Las respuestas no incluyen hosts, URLs, SQL, trazas ni secretos. Cada respuesta lleva `X-Request-ID` (se acepta el del cliente si cumple `[A-Za-z0-9._-]{1,64}`; si no, se genera) y produce un log JSON con `request_id`, método, ruta sin query string, status y `duration_ms`.

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
git clone https://github.com/manuXD270516/fintech-ai-reconciliation-agent.git
cd fintech-ai-reconciliation-agent
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
| `smoke` | Compose real (ver [evidencia](openspec/changes/bootstrap-mvp-foundation/evidence/README.md)) |

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

Son las versiones verificadas juntas en este repositorio; no se afirma que sean las últimas.

## Estructura

```text
apps/api/          adaptador HTTP (FastAPI): salud y /v1 con JWT/RBAC; Dockerfile (runtime + smoke)
apps/worker/       relay de outbox, consumidores JetStream (runs, ingestion por eventos) y DLQ
packages/domain/   dominio puro: Money, observaciones, revisiones, lotes, ingestion, reglas rules/v1
packages/store/    SQLAlchemy Core + migraciones Alembic; ingesta atómica, runs, outbox/inbox
packages/knowledge/ corpus, chunking, embeddings locales, retrieval híbrido y evaluación (M3)
datasets/          datasets sintéticos versionados con manifest (scripts/generate_synthetic.py)
infra/             init idempotente de PostgreSQL y configuración de NATS
scripts/           doctor, gate, smoke, trazabilidad, política, gate negativo
tests/unit         contratos y propiedades sin infraestructura
tests/integration  ejecutados dentro de la red Compose contra servicios reales
openspec/          specs vigentes, changes activos y archivados (+ evidence/)
docs/              diseño M0–M10 y decisiones de implementación
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

Todo objetivo de precisión, latencia o tokens de esos documentos es **EXPECTED**; nada se ha medido todavía. Los únicos datos **MEASURED** son los tiempos del smoke local de infraestructura de M0, con el alcance descrito en su evidencia; no son un benchmark.

## Change OpenSpec

[bootstrap-mvp-foundation](openspec/changes/bootstrap-mvp-foundation/proposal.md) especifica M0: [requirements](openspec/changes/bootstrap-mvp-foundation/specs/repository-foundation/spec.md), [acceptance criteria](openspec/changes/bootstrap-mvp-foundation/acceptance-criteria.md) (estado y evidencia de cada AC), [design](openspec/changes/bootstrap-mvp-foundation/design.md), [tasks](openspec/changes/bootstrap-mvp-foundation/tasks.md) y [test strategy](openspec/changes/bootstrap-mvp-foundation/test-strategy.md). El archivo está confirmado; se pospone mientras AC06 siga PENDING.

[deterministic-reconciliation](openspec/changes/archive/2026-10-01-deterministic-reconciliation/proposal.md) (M2) está archivado con AC01–AC11 en PASS; su spec vigente es [openspec/specs/deterministic-reconciliation](openspec/specs/deterministic-reconciliation/spec.md).

[transaction-domain](openspec/changes/archive/2026-09-29-transaction-domain/proposal.md) (M1) está archivado con AC01–AC09 en PASS ([evidencia](openspec/changes/archive/2026-09-29-transaction-domain/evidence/README.md)); su spec vigente es [openspec/specs/transaction-domain](openspec/specs/transaction-domain/spec.md).

## Límites de la demostración

Datos y proveedores sintéticos. Sin PAN, CVV, credenciales reales, dinero real ni ejecución de reembolsos o ajustes contables. El sistema conserva observaciones y evidencia; no sustituye al ledger ni al procesador de pagos. Toda decisión operativa exige una identidad humana autorizada, incluso si la IA expresa alta confianza. M0 no tiene autenticación de usuarios: sólo es apto para uso local en loopback, nunca para despliegue público.
