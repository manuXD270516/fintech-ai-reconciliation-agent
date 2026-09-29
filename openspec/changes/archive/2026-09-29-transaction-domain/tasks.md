## 1. Dominio puro

- [x] 1.1 Implementar `Money` y política de monedas versionada; verificar T01 (AC01).
- [x] 1.2 Implementar `TransactionObservation`, `ScopedRef`, `DualTime` y hash canónico sin imports de infraestructura; verificar T02 (AC02).
- [x] 1.3 Implementar la política de revisiones; verificar T03 (AC03).
- [x] 1.4 Implementar `ReconciliationBatch` y vocabularios versionados; verificar T04/T05 (AC04/AC05).

## 2. Fixtures

- [x] 2.1 Generador sintético determinístico, dataset `transactions-v1` y manifest; verificar T06 (AC06).

## 3. Persistencia

- [x] 3.1 Tablas SQLAlchemy Core, migración Alembic `0001` y job Compose `migrate` con privilegios mínimos; verificar T08 (AC08).
- [x] 3.2 Ingesta atómica con auditoría y outbox y serialización por clave; verificar T07 (AC07).

## 4. Cierre

- [x] 4.1 Ejecutar el gate completo, enlazar evidencia y archivar el change; verificar T09 (AC09).
