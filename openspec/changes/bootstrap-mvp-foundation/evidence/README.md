# Evidencia — bootstrap-mvp-foundation (M0)

Resultados reales de T01–T13 del 2026-09-29. Los tiempos son **MEASURED** sólo para este stack local de infraestructura en esta máquina; no son benchmarks ni se extrapolan a precisión, IA o producción.

## Entorno y commit

| Elemento | Valor |
|---|---|
| Commit del código probado | `6b462c0` (árbol limpio; `dirty: false` en los JSON). El gate estático se repitió en `022ab98`, tras ajustar la regla de trazabilidad y los artefactos: [log](gate-static-final.log) |
| Host | Windows 11 (10.0.26200) AMD64, Docker Desktop con Docker 29.8.0 linux/amd64, kernel WSL2 6.6.87.2, Compose 5.5.1 |
| Linux (T01) | Contenedor Debian 13 (trixie) x86_64 sobre el mismo kernel WSL2 |
| Toolchain | uv 0.12.20, CPython 3.12.14 (gestionado por uv), Node 22.23.1, OpenSpec 1.11.0 |
| No probado | arm64 y macOS; Linux nativo fuera de WSL2; ejecución en GitHub Actions |

Archivos: [gate completo en el árbol de trabajo](gate-all-worktree.log), [smoke del árbol de trabajo](smoke-worktree.json), [clone limpio Windows](t01-windows-clean-clone.log) con su [smoke](smoke-windows-clean-clone.json) y [script](t01-windows-clean-clone.ps1), [clone limpio Linux](t01-linux-clean-clone.log) con su [script](t01-linux-clean-clone.sh). Las rutas del perfil de usuario se reemplazaron por `%USERPROFILE%`.

## Resultados

| ID | Resultado | Qué se ejecutó | Evidencia |
|---|---|---|---|
| <a id="t01"></a>T01 | PASS | Windows: clone limpio con cachés vacías de uv/npm y proyecto Compose aislado (`recon-m0-clean`, puerto 18081); `uv sync --locked`, `npm ci`, `doctor`, `gate static` (8/8) y `gate smoke` (11/11); luego se borraron sólo sus volúmenes. Linux: clone limpio; uv descargó CPython 3.12.14 para Linux aunque la imagen trae `/usr/bin/python3`; `gate static` 8/8. | [Windows](t01-windows-clean-clone.log), [Linux](t01-linux-clean-clone.log) |
| <a id="t02"></a>T02 | PASS | `doctor` en Linux sin Docker: `[FAIL] docker` y `[FAIL] compose` con acción, exit 1. Unit tests de `doctor` con uv, Docker o Node ausentes y con versiones no soportadas. Sin `.env`: `docker compose config` falla con `required variable POSTGRES_DB is missing a value: set POSTGRES_DB in .env (copy .env.example)` y el smoke termina con `[FAIL] preflight: .env missing: copy .env.example to .env` (exit 1). | [Linux](t01-linux-clean-clone.log), `tests/unit/test_doctor_and_policy.py` |
| <a id="t03"></a>T03 | PASS | Dentro de la red Compose: pgvector 0.8.6, consulta KNN, tipo `vector` usable por el rol runtime; el rol runtime no puede `CREATE EXTENSION`/`DROP EXTENSION`/`CREATE SCHEMA`/`CREATE TABLE`/`CREATE ROLE`/`CREATE DATABASE` y no tiene atributos privilegiados; JetStream con stream de archivo, publicación, deduplicación por `Nats-Msg-Id`, consumo durable y ack con 0 pendientes. `db-init` re-ejecutado 2 veces más con exit 0; además, 5 inicializaciones con volumen nuevo, todas con exit 0. | [smoke](smoke-worktree.json) |
| <a id="t04"></a>T04 | PASS | Marcador en PostgreSQL y mensaje pendiente (`num_pending: 1`) → `docker compose --profile smoke stop` (todo detenido) → `up -d` → marcador intacto, 1 pendiente, payload correcto, ack → 0 pendientes; volúmenes con la misma fecha de creación; se limpiaron sólo el schema y el stream de la ejecución. | [smoke](smoke-worktree.json) |
| <a id="t05"></a>T05 | PASS | Desde el host: live y ready 200, claves exactas del body, `X-Request-ID` igual al body, sin header `Server`, sin secretos, `://`, puertos, hosts ni `Traceback`. Ready tardó 0.008 s. También test de integración con dependencias reales y contratos unitarios. | [smoke](smoke-worktree.json) |
| <a id="t06"></a>T06 | PASS | Ver tabla de degradación. También se probaron con dependencias reales: base de datos sin extensión `vector` (503, `vector: fail`), NATS sin JetStream (503, `messaging: fail`) y servidores TCP que aceptan conexión sin responder (503 con `timeout` en ≤ 3 s). Los unit tests incluyen un probe que tarda 2 s en cancelarse sin retrasar la respuesta. | [smoke](smoke-worktree.json) |
| <a id="t07"></a>T07 | PASS | Unit: campos ausentes o inválidos nombran sólo la variable; un canario no aparece. Proceso real `python -m recon_api` con config inválida: exit 2. Imagen Docker sin env: exit 2 y la lista de los 7 campos requeridos. Con canario en `APP_NATS_URL`, contraseña corta y timeout 9: exit 2, tres campos nombrados y el canario no se filtra. Tras esta prueba se eliminó del mensaje la longitud de las contraseñas. | `tests/unit/test_config.py` |
| <a id="t08"></a>T08 | PASS | Puertos publicados: sólo `api` en `127.0.0.1:<API_HOST_PORT>`; `postgres`, `nats` y `nats-nojs` sin puertos; red `backend` con `internal: true`; la API no responde en la IP LAN del host; los valores secretos de `.env` no aparecen en logs de ningún servicio, ni en `db-init` ni en los bodies. `policy`: `.env` ignorado, `.env.example` sólo `dev-only-*`, sin claves ni PAN Luhn-válidos en archivos versionados. | [smoke](smoke-worktree.json), [gate](gate-all-worktree.log) |
| <a id="t09"></a>T09 | PASS | Unit: ID válido propagado; ausente generado; malformados (inyección JSON con salto de línea, 65 caracteres, espacios, vacío, `;`) reemplazados sin líneas forjadas; query string y canario ausentes del log. Stack real: `X-Request-ID: smoke-00ea43059a3f` aparece en exactamente una línea JSON con `status 200`, `path /health/ready` y `duration_ms 8.39`. | `tests/unit/test_request_logging.py`, [smoke](smoke-worktree.json) |
| <a id="t10"></a>T10 | PASS local · CI PENDING | Los mismos 9 pasos de `scripts/gate.py` pasan en el árbol de trabajo (Windows), en el clone limpio de Windows y en el de Linux (8 estáticos). El gate eliminó del entorno una variable de proveedor IA presente (`ANTHROPIC_BASE_URL`). Un test verifica que `ci.yml` ejecuta exactamente `GROUPS["all"]` en orden, sin `secrets.` y con actions fijadas por SHA. actionlint 1.7.12 no reporta problemas. **El workflow no se ha ejecutado en GitHub** (no hay remoto), así que no hay comparación real de códigos de salida en CI. | [gate](gate-all-worktree.log), `tests/unit/test_ci_parity.py` |
| <a id="t11"></a>T11 | PASS | Gate negativo sobre copias temporales: controles sin mutación pasan; fallan requirement sin escenarios, requirement sin SHALL/MUST, `test-strategy.md` eliminado, AC con RF inexistente, readiness 200 ante falla y ruta `/payments` añadida; el árbol real no cambia (hash). Unit tests: falta de cada artefacto, referencias desconocidas, PASS sin evidencia o con evidencia inexistente, estado inválido, tarea marcada sin evidencia y archivado incompleto. | [gate](gate-all-worktree.log), `tests/unit/test_traceability_gate.py` |
| <a id="t12"></a>T12 | PASS | Catálogo de rutas = `/health/live`, `/health/ready`, `/docs`, `/docs/oauth2-redirect`, `/openapi.json`; OpenAPI documenta sólo las dos rutas de salud. Revisión manual del README: declara sólo M0, marca M1–M10 como diseño y los objetivos como EXPECTED; los únicos datos MEASURED son los de esta evidencia. | `tests/unit/test_scope.py`, [README](../../../../README.md) |
| <a id="t13"></a>T13 | PASS | `check_traceability.py` OK: seis artefactos, AC → RF/T/tasks existentes y todos cubiertos, PASS con evidencia existente, tareas marcadas respaldadas. El change no se archivó y `openspec/specs/` sigue vacío (pendiente de tu confirmación). | [gate](gate-all-worktree.log) |

### Degradación medida (T06, árbol de trabajo)

Tres peticiones a `/health/ready` por caso, con `APP_READY_TIMEOUT_SECONDS=2.5`:

| Caso | Ready | Máximo | Live | Estados | Recuperación |
|---|---|---|---|---|---|
| `docker compose stop postgres` | 503 ×3 | 2.504 s | 200 | database/vector `timeout` | 1.02 s tras `start` |
| `docker compose pause postgres` | 503 ×3 | 2.517 s | 200 | database/vector `timeout` | 0.04 s tras `unpause` |
| `docker compose stop nats` | 503 ×3 | 2.527 s | 200 | messaging `timeout` | 0.01 s |
| `docker compose pause nats` | 503 ×3 | 2.530 s | 200 | messaging `timeout` | 0.01 s |

En el clone limpio de Windows, los máximos fueron 2.504–2.527 s. Con un servicio detenido, el estado es `timeout` y no `fail`: la resolución DNS del nombre del contenedor en la red interna no falla rápido, así que manda el deadline global.

## Otros hallazgos y verificaciones

- **Carrera corregida** (`50fb032`): en el primer clone limpio, `db-init` salió con exit 2. En un volumen nuevo, la imagen de PostgreSQL arranca un servidor temporal que sólo escucha por socket Unix, y el healthcheck por socket lo daba por sano. El healthcheck pasó a TCP `127.0.0.1`. En el árbol de trabajo no apareció porque el volumen ya estaba inicializado.
- `pip-audit` 2.10.1 (ejecutado ad hoc, no es dependencia) sobre el lock exportado (runtime + dev): "No known vulnerabilities found". `npm audit`: 0 vulnerabilidades. No se escanearon las imágenes de contenedor.
- Limitación de OpenSpec 1.11.0: `--strict` acepta un escenario cuyo encabezado cambia de `#### Scenario:` a otro `####`. Por eso el gate negativo elimina escenarios en lugar de renombrarlos.
- Limitación de T01 en Windows: uv reutilizó el CPython 3.12.14 ya instalado en el perfil a pesar de `UV_PYTHON_INSTALL_DIR`; la descarga limpia de Python se ejercitó en Linux.
