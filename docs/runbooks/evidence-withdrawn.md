# Evidencia retirada

**Disparadores:**
- Un documento de conocimiento resulta incorrecto, confidencial o mal clasificado.
- La alerta `ToolPermissionRefused`: una tool MCP fue rechazada por scope o tenant en la última hora, lo que puede indicar un intento de acceso indebido o un ACL mal configurado.

## Retirar un documento

```text
docker compose run --rm --no-deps knowledge-ingest python -m recon_knowledge revoke --document-id DOC-ID --version N --actor ops-ana --reason "motivo"
```

- El documento pasa a `review_status = revoked` y **no se borra**. Todas las ramas de retrieval (FTS, código de error y vector) filtran por `published`, así que deja de aparecer en búsquedas nuevas en el acto.
- La revocación se audita (`knowledge.revoke`, actor y motivo) en la misma transacción.
- Las investigaciones y recomendaciones ya existentes conservan sus citas para la auditoría. Si una recomendación pendiente cita el documento, el supervisor debe rechazarla o pedir información con el motivo "evidencia retirada". El sistema no la invalida automáticamente; es una limitación conocida.

## `ToolPermissionRefused`

```text
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT occurred_at, actor, action, outcome FROM recon.audit_entries WHERE resource_type = '"'"'mcp_tool'"'"' AND outcome = '"'"'FORBIDDEN'"'"' ORDER BY id DESC LIMIT 20"'
```

Revisar qué identidad de servicio (`MCP_SUBJECT`) y qué scopes estaban configurados. Un `FORBIDDEN` es un rechazo correcto, no una filtración: los recursos de otro tenant son indistinguibles de inexistentes. La alerta se apaga sola una hora después del último rechazo.
