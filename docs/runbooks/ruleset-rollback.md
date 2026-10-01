# Rollback de ruleset

**Estado actual:** sólo existe `rules/v1`, así que este runbook no se ejercitó y describe el procedimiento previsto.

Cada run guarda `ruleset_version` y el `snapshot_hash` de sus entradas, y sus resultados nunca se reescriben. Volver a un ruleset anterior equivale a:

1. Desplegar la imagen anterior: reconstruir desde el commit previo con `docker compose up -d --build api worker`.
2. Pedir un run nuevo de cada lote afectado (`POST /v1/batches/{id}/runs`). El run anterior queda como historia y las recomendaciones basadas en él pasan a obsoletas: M6 rechaza decidir sobre un run que dejó de ser el más reciente.
3. Comparar conteos por `match_status` entre ambos runs (`GET /v1/runs/{id}`) y registrar el motivo en el caso o ticket correspondiente.

Nunca se modifica un run existente ni se borran resultados.
