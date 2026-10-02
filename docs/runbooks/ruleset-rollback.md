# Rollback de ruleset

**Estado:** ejercitado en el smoke (`M11-T03`) con `rules/v2`, una variante **sintética** que existe sólo para este drill: aplica referencias fuertes, pero no hace ranking débil. `rules/v1` sigue siendo el ruleset por defecto y el que usan las evaluaciones.

Cada run guarda el `ruleset_version` vigente al pedirlo y el `snapshot_hash` de sus entradas. Sus resultados nunca se reescriben. El ruleset de los runs nuevos se elige al desplegar con `APP_RULESET` (`rules/v1` por defecto).

## Procedimiento

1. **Volver a desplegar con el ruleset anterior.** Para una versión de reglas que sigue en la imagen, basta cambiar la configuración:

   ```text
   APP_RULESET=rules/v1 docker compose up -d api
   ```

   Si la versión anterior sólo existe en una imagen previa, hay que reconstruir desde ese commit con `docker compose up -d --build api worker`.
2. **Pedir un run nuevo de cada lote afectado** (`POST /v1/batches/{id}/runs`). El run anterior queda como historia. Las recomendaciones basadas en él quedan obsoletas: decidir sobre ellas devuelve 409 `recommendation_obsolete`, porque su run dejó de ser el más reciente.
3. **Comparar** los conteos por `match_status` de ambos runs (`GET /v1/runs/{id}`). Con las mismas entradas, el `snapshot_hash` debe ser idéntico. Registrar el motivo en el caso o ticket correspondiente.

## Qué verifica el drill `M11-T03`

- Un lote corrido con `rules/v2` registra ese ruleset y no tiene PROBABLE.
- Tras el rollback a `rules/v1`, un run nuevo del mismo lote tiene el mismo snapshot y recupera los PROBABLE.
- Los resultados del run de `rules/v2` no cambian.
- La decisión sobre una recomendación del run de `rules/v2` se rechaza con `recommendation_obsolete`.

Nunca se modifica un run existente ni se borran resultados.
