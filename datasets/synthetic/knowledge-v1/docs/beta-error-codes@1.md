---
document_id: beta-error-codes
version: 1
tenant_scope: global
acl: analyst,supervisor,auditor
provider_id: prov-beta
document_type: error_codes
title: Códigos de error de prov-beta
language: es
effective_from: 2026-01-01T00:00:00+00:00
published_at: 2026-01-01T00:00:00+00:00
review_status: published
---
# Códigos de error de prov-beta

Códigos que prov-beta publica en su archivo diario. Documento sintético.

## B12 — Pago en espera de confirmación

El pago figura con estado WAIT mientras el banco emisor confirma. Puede pasar a OK o KO en el reporte del día siguiente; no es un faltante definitivo.

## B19 — Comisión descontada en liquidación

prov-beta liquida neto para cuentas con plan comercial "neto". El importe reportado es bruto menos comisión fija de 1.50 en la moneda del cobro.

## B27 — Referencia de comercio duplicada

Dos cobros distintos comparten la misma referencia de comercio. prov-beta los procesa como cobros independientes; no son un reenvío técnico.

## B31 — Estado desconocido en reporte

El archivo contiene un estado fuera del vocabulario publicado. Debe tratarse como error de procesamiento hasta que prov-beta confirme el significado.
