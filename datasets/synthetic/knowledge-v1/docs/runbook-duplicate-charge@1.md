---
document_id: runbook-duplicate-charge
version: 1
tenant_scope: global
acl: analyst,supervisor,auditor
document_type: runbook
title: Runbook de cobro duplicado
language: es
effective_from: 2026-01-01T00:00:00+00:00
published_at: 2026-01-01T00:00:00+00:00
review_status: published
---
# Runbook de cobro duplicado

Aplica a DUPLICATE_CANDIDATE. Documento sintético.

## Duplicado económico frente a reenvío técnico

Un reenvío técnico repite el mismo registro (misma revisión y hash) y la ingesta lo descarta sin efectos. Un duplicado económico son dos cobros distintos con la misma referencia de comercio: nunca se deduplican automáticamente porque pueden representar dinero real cobrado dos veces.

## Pasos

1. Comparar source_record_id, attempt_ref e importes de ambos registros.
2. Consultar si el proveedor informó B27 o E17 para la referencia.
3. Escalar a un supervisor; un posible reembolso requiere decisión humana y queda fuera del sistema.
