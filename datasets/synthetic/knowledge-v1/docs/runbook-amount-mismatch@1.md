---
document_id: runbook-amount-mismatch
version: 1
tenant_scope: global
acl: analyst,supervisor,auditor
document_type: runbook
title: Runbook de diferencia de importe
language: es
effective_from: 2026-01-01T00:00:00+00:00
published_at: 2026-01-01T00:00:00+00:00
review_status: published
---
# Runbook de diferencia de importe

Aplica cuando el motor reporta AMOUNT_MISMATCH entre el ledger interno y el reporte del proveedor para la misma referencia. Documento sintético.

## Principios

La diferencia en unidades menores es un hecho. Cualquier explicación (comisión, liquidación neta, reverso parcial) es una hipótesis hasta encontrar evidencia aplicable a esa cuenta y fecha. Nunca ajustar el importe ni cerrar la discrepancia automáticamente.

## Pasos de investigación

1. Confirmar que ambas observaciones comparten moneda, cuenta y tipo de operación.
2. Revisar si el contrato de la cuenta declara liquidación neta (prov-alfa E21, prov-beta B19).
3. Buscar reversos parciales o refunds enlazados al mismo pago.
4. Consultar incidentes del proveedor en la fecha de la operación.
5. Documentar hechos, inferencias e hipótesis por separado y proponer el siguiente paso a un humano.

## Qué no hacer

No sumar comisiones estimadas para "cerrar" la diferencia. No tratar un incidente parecido como prueba de que el pago actual fue afectado.
