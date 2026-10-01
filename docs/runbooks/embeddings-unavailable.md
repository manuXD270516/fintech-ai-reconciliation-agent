# Embeddings o investigador no disponibles

**Alerta:** `InvestigatorHeartbeatMissing` (investigador sin latido > 60 s).

**Contexto:** los embeddings son locales (hashing de 256 dimensiones, sin red), así que no hay un proveedor externo que pueda caerse. Lo que puede fallar es el proceso `investigator`, el servidor MCP que lanza o, si se activó el perfil `ollama`, el modelo local.

**Impacto:** la conciliación determinística sigue funcionando; ese es el kill switch de la IA. Las investigaciones quedan en `REQUESTED` y, tras 3 entregas fallidas, en `FAILED` con el motivo. Ninguna decisión depende de que exista un borrador.

## Diagnóstico

```text
docker compose ps investigator
docker compose logs --tail 50 investigator
curl -s http://127.0.0.1:18180/metrics | findstr "recon_investigations heartbeat"
```

## Mitigación

1. Proceso caído: `docker compose up -d investigator`.
2. Modelo local con fallas (perfil `ollama`): volver al proveedor scripted con `RECON_MODEL_PROVIDER=scripted docker compose up -d investigator`.
3. Kill switch de la IA: `docker compose stop investigator`. Los analistas trabajan sobre los resultados determinísticos y, si hace falta, proponen sin adoptar borrador. Las investigaciones pendientes se retoman al volver a arrancarlo: el claim con lease evita la doble ejecución.

## Verificación

El latido vuelve a menos de 60 s. Una investigación nueva llega a `DRAFTED`, `ABSTAINED` o `ESCALATED`.
