## Context

M1 entregó `recon_domain` (dinero, observaciones, revisiones, lotes, mappings) y `recon_store` (ingesta atómica con auditoría y outbox). M2 implementa el pipeline determinístico de [docs/01-domain.md](../../../docs/01-domain.md#pipeline-determinístico-propuesto), el patrón outbox/inbox de ADR-004 en [docs/02-architecture.md](../../../docs/02-architecture.md) y la autenticación de D07 en [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md).

## Goals / Non-Goals

**Goals:** casos RC01–RC13 de [docs/07-evals.md](../../../docs/07-evals.md) resueltos determinísticamente; reproducibilidad por snapshot; at-least-once sin efectos duplicados; API autenticada mínima.

**Non-Goals:** 1:N, fees/FX, UI, investigación con IA.

## Decisions

- **Reglas puras.** `recon_domain.reconciliation.reconcile(RunInput) -> list[Outcome]` no hace I/O. El store arma el snapshot (revisión vigente por clave con `DISTINCT ON`) y persiste los resultados. Orden estable por `(payment_ref, operation, ids)`; un test baraja la entrada y exige el mismo resultado.
- **Oráculo independiente.** `recon_domain.oracle.run_files` ejecuta ingestion + reglas en memoria sobre el dataset etiquetado; el test de integración y el smoke exigen que el camino persistido (HTTP → outbox → NATS → worker) produzca la misma clasificación que las etiquetas.
- **Dataset v2.** v1 etiquetaba como EXACT pares con diferencias, contradiciendo el invariante 4. v1 queda congelado (sus archivos se siguen regenerando idénticos) y v2 corrige sólo esas etiquetas; un test lo verifica.
- **Ingestion por eventos.** Cada evento se trata como un artefacto de una fila con clave `evt-<event_id>`; la idempotencia del artefacto sustituye al inbox para este consumidor. El tenant, la fuente y el proveedor vienen del subject (`recon.ingest.<tenant>.<source>.<provider>`), que en un despliegue real se restringe con permisos NATS por integración; localmente hay un solo usuario NATS (limitación documentada).
- **Dead letters.** `PoisonMessageError` (envelope malformado) va directo a `recon.dlq.<consumer>` y se termina el mensaje; los fallos transitorios se reintentan con backoff exponencial hasta `MAX_DELIVER=5` y luego se envían a DLQ (un run agotado queda `failed`).
- **Privilegios.** Migración `0002` concede al rol runtime `SELECT, INSERT` en artefactos, cuarentena, resultados e inbox, y `UPDATE` sólo de columnas de estado del run. Resultados y cuarentena son append-only para la aplicación.
- **Auth.** `scripts/dev_auth.py` genera un par RS256 en `.dev-keys/` (ignorado por git); sólo el JWKS público se monta en el contenedor. El verificador exige `exp`, `iat`, `sub`, `iss`, `aud`, `kid` conocido y algoritmo RS256 (rechaza `alg=none` y claves ajenas). Sin JWKS la API arranca con error de configuración; sin verificador las rutas responden 503 (fail-closed).

## Risks / Trade-offs

- El ranking débil es heurístico y no calibrado: se publica como `score` de ranking, nunca como probabilidad.
- La ventana de deduplicación de JetStream (120 s) no reemplaza al inbox: la corrección depende del inbox/idempotencia en base de datos.
- Las claves de desarrollo no son un IdP; sirven para loopback. El verificador es compatible con un JWKS de OIDC real.
