---
document_id: incident-inc-0815
version: 1
tenant_scope: global
acl: analyst,supervisor,auditor
provider_id: prov-alfa
document_type: incident
title: INC-0815 liquidación neta inesperada en prov-alfa
language: es
effective_from: 2026-08-15T00:00:00+00:00
published_at: 2026-08-16T00:00:00+00:00
review_status: published
---
# INC-0815 liquidación neta inesperada en prov-alfa

Incidente histórico sintético. Describe un caso pasado; no prueba que un pago actual haya sido afectado.

## Resumen

Entre el 2026-08-15 y el 2026-08-16 prov-alfa liquidó neto (E21) tres cuentas que tenían plan bruto por un error de configuración del proveedor. El ledger interno mostraba el importe bruto y el motor reportó AMOUNT_MISMATCH.

## Resolución

prov-alfa corrigió la configuración y emitió un ajuste en el reporte del 2026-08-18. La decisión de aceptar el ajuste fue tomada por un supervisor después de comparar el reporte corregido.
