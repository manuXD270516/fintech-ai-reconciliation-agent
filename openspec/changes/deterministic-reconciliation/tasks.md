## 1. Ingestion

- [x] 1.1 Parser CSV versionado con cuarentena por fila y dataset `transactions-v2`; verificar T01/T03 (AC01, AC02).
- [x] 1.2 Recepción idempotente por HTTP y por eventos JetStream con tenant del canal; verificar T04/T05 (AC01, AC07).

## 2. Motor determinístico

- [x] 2.1 Reglas `rules/v1`: exactos, discrepancias enlazadas, ranking débil, faltantes, duplicados y errores; verificar T02/T03 (AC03, AC04, AC05).
- [x] 2.2 Runs versionados con snapshot hash y resultados persistidos; verificar T04 (AC06).

## 3. Mensajería y API

- [x] 3.1 Worker con relay de outbox, inbox y dead letters; verificar T05 (AC07).
- [x] 3.2 API `/v1` autenticada con JWT/RBAC y catálogo de rutas; verificar T06 (AC08).
- [x] 3.3 Migración `0002` con privilegios mínimos; verificar T08 (AC09).

## 4. Cierre

- [x] 4.1 E2E Compose contra el oráculo, auditoría de imports sin IA, gate completo y archivo; verificar T07/T09 (AC10, AC11).
