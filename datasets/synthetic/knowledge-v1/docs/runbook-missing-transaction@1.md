---
document_id: runbook-missing-transaction
version: 1
tenant_scope: global
acl: analyst,supervisor,auditor
document_type: runbook
title: Runbook de transacción faltante
language: es
effective_from: 2026-01-01T00:00:00+00:00
published_at: 2026-01-01T00:00:00+00:00
review_status: published
---
# Runbook de transacción faltante

Aplica a WAITING_SOURCE, MISSING_INTERNAL y MISSING_EXTERNAL. Documento sintético.

## Espera frente a ausencia

Un timeout o un archivo todavía no recibido no prueban ausencia. Mientras el lote no alcance su cutoff o la fuente contraria no esté marcada completa, el resultado correcto es WAITING_SOURCE.

## Faltante confirmado

Con la ventana cerrada y ambas fuentes completas, verificar la dirección: MISSING_EXTERNAL significa que el ledger registró el pago y el proveedor no lo reportó; MISSING_INTERNAL es el caso inverso. Solicitar al proveedor el registro de la referencia antes de proponer cualquier ajuste.

## Llegadas tardías

Si la observación llega después de un run, se ejecuta un run nuevo. Las recomendaciones basadas en el run anterior quedan obsoletas y no pueden aprobarse.
