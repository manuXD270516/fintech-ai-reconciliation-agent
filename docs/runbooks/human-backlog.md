# Backlog humano

**Alerta:** `HumanBacklog`: una recomendación lleva más de 24 h esperando decisión (`recon_human_queue_oldest_age_seconds`).

**Impacto:** la recomendación sigue pendiente y puede expirar o quedar obsoleta si llega un run más nuevo. El sistema no decide nunca por omisión.

## Acciones

1. Revisar la cola en el dashboard (`#/cases`, filtro `HUMAN_REVIEW`) o en `GET /v1/cases?status=HUMAN_REVIEW`.
2. Asignar a un supervisor que no haya propuesto la recomendación ni pedido la investigación, por segregación de funciones.
3. Si la recomendación expiró o quedó obsoleta, el analista propone una nueva sobre la versión vigente.

**Qué NO hacer:** no aprobar en lote (la UI no lo permite a propósito) ni bajar el umbral para silenciar la alerta.
