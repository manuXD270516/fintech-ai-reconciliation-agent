---
document_id: alfa-error-codes
version: 2
tenant_scope: global
acl: analyst,supervisor,auditor
provider_id: prov-alfa
document_type: error_codes
title: Códigos de error de prov-alfa
language: es
effective_from: 2026-06-01T00:00:00+00:00
published_at: 2026-06-01T00:00:00+00:00
review_status: published
supersedes: alfa-error-codes@1
---
# Códigos de error de prov-alfa

Catálogo vigente de códigos que prov-alfa incluye en su reporte de liquidación. Documento sintético para la demo.

## E05 — Autorización expirada

La autorización venció antes de la captura. El reporte muestra estado DECLINED y no existe dinero capturado. No esperar una liquidación posterior para ese intento.

## E17 — Captura duplicada detectada

prov-alfa detectó una segunda captura con la misma referencia de comercio y la rechazó. No reintentar la captura. Verificar en el ledger interno si existen dos registros de captura para el mismo pago y abrir revisión de duplicado.

## E21 — Liquidación neta de comisión

La liquidación se informa neta: el importe reportado ya descuenta la comisión del adquirente. La diferencia contra el importe bruto del ledger corresponde a la comisión sólo si el contrato de la cuenta declara liquidación neta.

## E33 — Moneda no soportada para la cuenta

La cuenta de comercio no admite la moneda del cobro. prov-alfa no convierte monedas: el cobro queda rechazado y no debe compararse contra registros en otra moneda.

## E40 — Reverso parcial

Se reversó sólo una parte de la captura. El reverso aparece como operación separada con su propio importe; no reemplaza a la captura original.
