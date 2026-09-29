## Why

La conciliación determinística (M2) necesita un modelo de dominio exacto y persistente antes de comparar fuentes: dinero sin floats, observaciones inmutables acotadas por proveedor y cuenta, revisiones idempotentes y lotes con ventanas explícitas. Sin estas invariantes cualquier regla posterior podría producir matches falsos o sobrescribir historia.

## What Changes

- Implementar **M1 — Transaction domain model** en `packages/domain` (`recon_domain`), sin imports de HTTP, base de datos, bus ni LLM.
- `Money` exacto en unidades menores con exponente por moneda versionado (`currency-policy/v1`, USD y BOB), conversión decimal exacta y rechazo de precisión excesiva, floats y overflow de 64 bits.
- `TransactionObservation` inmutable con referencias acotadas por proveedor/cuenta, `DualTime` (UTC + offset original) y `raw_hash` canónico.
- Política de revisiones: replay idéntico sin efecto, conflicto ante mismo ID/revisión con otro hash, nueva revisión y revisión tardía conservada como historia.
- `ReconciliationBatch` con ventana `[inicio, fin)`, zona horaria de negocio, par de fuentes y cutoff.
- Vocabularios versionados (`mappings/v1`) por fuente y proveedor ficticio; valores desconocidos se rechazan.
- Dataset sintético versionado y determinístico (`datasets/synthetic/transactions-v1`) con manifest, hash de contenido y etiquetas por escenario.
- Persistencia en `packages/store` (`recon_store`) con SQLAlchemy 2 Core + Alembic: tablas en esquema `recon`, ingesta atómica (estado + auditoría + outbox) y privilegios mínimos para el rol runtime. Job `migrate` en Compose.

## Capabilities

### New Capabilities

- `transaction-domain`: el sistema representa y persiste observaciones de transacciones sintéticas con dinero exacto, identidad acotada, revisiones idempotentes, lotes de conciliación y fixtures versionados.

### Modified Capabilities

Ninguna. `repository-foundation` (M0) sigue sin archivar; este change sólo añade el job `migrate` antes de la API sin cambiar su contrato de salud.

## Impact

Nuevos paquetes `packages/domain` y `packages/store`, migración `0001_transaction_domain`, servicio Compose `migrate`, dataset sintético y tests unitarios/integración. La imagen de la API incluye los paquetes nuevos. No se añaden endpoints HTTP.

Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md).

## Non-goals

Ingestion por CSV/API/eventos, normalización de archivos, reglas de matching, discrepancias, outbox relay y cualquier endpoint pertenecen a M2. FX, fees, netting y relaciones 1:N quedan fuera del MVP. Ningún componente de M1 usa IA ni mueve dinero.
