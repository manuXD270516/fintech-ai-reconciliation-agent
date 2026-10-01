---
document_id: beta-settlement-guide
version: 1
tenant_scope: global
acl: analyst,supervisor,auditor
provider_id: prov-beta
document_type: provider_doc
title: Guía de liquidación de prov-beta
language: es
effective_from: 2026-01-01T00:00:00+00:00
published_at: 2026-01-01T00:00:00+00:00
review_status: published
---
# Guía de liquidación de prov-beta

Documentación sintética del proveedor ficticio prov-beta.

## Planes de liquidación

Las cuentas con plan "neto" reciben el importe bruto menos una comisión fija de 1.50 por cobro (código B19). Las cuentas con plan "bruto" reciben el importe completo y la comisión se factura aparte a fin de mes.

## Estados del archivo diario

OK indica cobro liquidado, WAIT espera de confirmación del emisor (B12), KO rechazo definitivo y VOID anulación. Cualquier otro valor es un estado desconocido (B31).
