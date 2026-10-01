---
document_id: alfa-settlement-guide
version: 1
tenant_scope: global
acl: analyst,supervisor,auditor
provider_id: prov-alfa
document_type: provider_doc
title: prov-alfa settlement guide
language: en
effective_from: 2026-07-01T00:00:00+00:00
published_at: 2026-07-01T00:00:00+00:00
review_status: published
---
# prov-alfa settlement guide

Synthetic provider documentation for the demo.

## Gross and net settlement

Since 2026-07-01 merchant accounts on the "net" plan are settled net of the acquirer fee. The settlement report then shows the captured amount minus a fee of 1% rounded down to the minor unit, flagged with error code E21. Accounts on the "gross" plan keep receiving the full captured amount.

## Report timing

The daily settlement file is published at 06:00 UTC and covers captures of the previous business day in America/La_Paz. Late captures appear in the next file; their absence before the cutoff is not a missing transaction.

## Currencies

prov-alfa settles USD and BOB separately and never converts between them (see E33).
