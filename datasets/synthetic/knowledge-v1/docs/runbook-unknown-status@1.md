---
document_id: runbook-unknown-status
version: 1
tenant_scope: global
acl: analyst,supervisor,auditor
document_type: runbook
title: Runbook de estado desconocido y cuarentena
language: es
effective_from: 2026-01-01T00:00:00+00:00
published_at: 2026-01-01T00:00:00+00:00
review_status: published
---
# Runbook de estado desconocido y cuarentena

Aplica a PROCESSING_ERROR por filas en cuarentena. Documento sintético.

## Cuarentena

Una fila con estado sin mapping, precisión inválida o alcance incorrecto queda en cuarentena con su código. El sistema nunca adivina el estado ni redondea importes.

## Resolución

1. Identificar el código de rechazo (unknown_mapping, invalid_precision, scope_violation).
2. Si el estado es nuevo, pedir al proveedor su definición y versionar el vocabulario (mappings/v2) con revisión.
3. Reingestar el artefacto corregido con una clave de idempotencia nueva.
