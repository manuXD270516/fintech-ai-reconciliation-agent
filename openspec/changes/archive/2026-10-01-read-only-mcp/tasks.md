## 1. Modelo de lectura

- [x] 1.1 Migración `0004` con `transaction_uid`, snapshots de proveedor y rol `recon_mcp` con privilegios mínimos; verificar T08 (AC09, AC10).

## 2. Servidor

- [x] 2.1 Contratos `tools/v1`, servidor MCP de bajo nivel y transporte stdio con SDK fijado; verificar T01/T02 (AC01, AC02).
- [x] 2.2 Identidad de servicio, autorización por recurso y envelope con procedencia; verificar T03/T04 (AC03, AC04).
- [x] 2.3 Errores estructurados, límites y paginación firmada; verificar T05/T06 (AC05, AC06, AC07).

## 3. Integración

- [x] 3.1 Backend SQL con retrieval híbrido y auditoría por el rol del servidor; verificar T07 (AC08, AC09).
- [x] 3.2 Gate completo, evidencia y archivo; verificar T09 (AC11).
