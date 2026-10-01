---
document_id: incident-inc-0902
version: 1
tenant_scope: global
acl: analyst,supervisor,auditor
provider_id: prov-beta
document_type: incident
title: INC-0902 retraso del archivo diario de prov-beta
language: es
effective_from: 2026-09-02T00:00:00+00:00
published_at: 2026-09-03T00:00:00+00:00
review_status: published
---
# INC-0902 retraso del archivo diario de prov-beta

Incidente histórico sintético.

## Resumen

El 2026-09-02 el archivo diario de prov-beta llegó con seis horas de retraso y muchos cobros figuraron con WAIT (B12). Varias conciliaciones ejecutadas antes de la llegada mostraron WAITING_SOURCE.

## Lección

No declarar faltantes antes del cutoff ni sin la marca de fuente completa. Ejecutar un run nuevo cuando llegue el archivo.
