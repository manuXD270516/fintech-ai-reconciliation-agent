## Context

M0 dejó API de salud, PostgreSQL 17 + pgvector y NATS JetStream en Compose. M1 añade el modelo de dominio y su persistencia, respetando [docs/01-domain.md](../../../../docs/01-domain.md), ADR-002/003 de [docs/02-architecture.md](../../../../docs/02-architecture.md) y las decisiones vinculantes de [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md) (D06: SQLAlchemy 2 Core + Alembic sobre psycopg 3).

## Goals / Non-Goals

**Goals:** invariantes de dinero, identidad, revisiones y lotes verificables con tests de propiedades y negativos; persistencia atómica con auditoría y outbox; migraciones versionadas; fixtures sintéticos reproducibles.

**Non-Goals:** ingestion de archivos, reglas de matching, relay del outbox, endpoints HTTP (M2+).

## Decisions

- **Paquetes separados.** `recon_domain` es Python puro (sólo `tzdata` para zonas IANA en Windows); un test AST prohíbe imports de infraestructura. `recon_store` depende del dominio, nunca al revés.
- **Dinero.** `Money(amount_minor: int, currency)` con `type(...) is int` para rechazar `bool`/`float`. Exponentes en `CURRENCY_EXPONENTS` inmutable (`currency-policy/v1`). Conversión con `Decimal.scaleb` y comprobación de integralidad: nunca se redondea.
- **Tiempo.** `DualTime(utc, offset_minutes)` conserva el offset reportado; timestamps naive se rechazan.
- **Revisiones.** `decide()` es una función pura sobre la historia de la clave; el store la aplica bajo `pg_advisory_xact_lock(hashtextextended(clave))` para serializar escritores de la misma clave sin bloquear otras.
- **Efectos.** CREATED/NEW_REVISION/STALE_REVISION insertan observación + auditoría + outbox (`ObservationRecorded` v1) en la misma transacción. CONFLICT sólo audita. DUPLICATE no escribe nada.
- **Esquema.** Tablas en el esquema `recon`; `tables.py` (Core) y la migración `0001` se comparan con `alembic.autogenerate.compare_metadata` en un test de integración para evitar drift.
- **Privilegios.** El job `migrate` usa el rol bootstrap; el rol runtime recibe `SELECT, INSERT` en observaciones y auditoría, `SELECT, INSERT, UPDATE` en lotes y `UPDATE` sólo de columnas de publicación en outbox. `PUBLIC` pierde acceso al esquema.
- **Fixtures.** `recon_domain.synthetic.generate(seed)` produce ledger interno, reporte de proveedor y etiquetas para 11 escenarios (exacto, mismatch de importe/estado, faltantes, duplicado, revisión fuera de orden, replay, precisión inválida, estado desconocido, referencia débil). Proveedores ficticios `prov-alfa` y `prov-beta`.

## Risks / Trade-offs

- Advisory locks por hash pueden colisionar entre claves distintas: sólo serializa de más, no rompe corrección.
- Ejecutar migraciones con el rol bootstrap es aceptable en local; una demo pública necesitaría un rol owner dedicado (M9).
- Los tests de integración corren sólo dentro del contenedor smoke (red interna), igual que en M0.
