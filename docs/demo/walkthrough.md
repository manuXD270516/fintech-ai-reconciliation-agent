# Walkthrough de la demo (M10)

Demo **local y sintética**: nada se publica ni se despliega y no se usan APIs pagas. Toma unos 15 minutos desde un clone limpio, más las descargas de imágenes la primera vez. Los prerrequisitos están en el [README](../../README.md#prerrequisitos).

## 1. Preparar

```text
uv sync --locked && npm ci && npm ci --prefix apps/web
Copy-Item .env.example .env            # bash: cp .env.example .env
uv run python scripts/dev_auth.py init  # claves JWT locales (.dev-keys/, ignorado por git)
docker compose up -d --build            # postgres, nats, migraciones, api, worker, investigator
curl http://127.0.0.1:18180/health/ready
```

## 2. Crear una sesión de demo aislada

```text
uv run python scripts/demo.py seed
```

El comando crea un tenant nuevo (`demo-xxxxxxxx`), ingiere por HTTP el dataset `transactions-v2` (44 pagos, 2 proveedores ficticios), crea y ejecuta los 12 lotes y compara cada resultado con las etiquetas del dataset (`matches_labels: true`). Los tokens de analista, supervisora y auditor de esa sesión quedan en `.demo/<tenant>.json`. Cada sesión es un tenant distinto: una sesión no puede leer los datos de otra, lo que verifica el smoke `M10-T03`.

## 3. Recorrer el flujo en el dashboard

```text
npm --prefix apps/web run dev           # http://127.0.0.1:18181
```

1. **Analista:** pegar el token `analyst` de la sesión, abrir el run indicado en `try_this` y elegir el resultado con `AMOUNT_MISMATCH`.
2. **Pedir investigación.** El investigador consulta evidencia sólo por las tools MCP de lectura y produce un borrador separado en hechos, inferencias e hipótesis, con citas. La confianza es `uncalibrated` y el modelo es el proveedor scripted: el resultado es **SIMULATED**.
3. **Abrir el caso y proponer** adoptando el borrador revisado.
4. **Supervisora:** pegar el token `supervisor`, abrir el caso (ver "Vigente") y registrar la decisión con motivo. El formulario muestra el efecto exacto: registra la decisión y **nunca mueve dinero**.
5. **Auditor:** abrir la auditoría del caso. Ahí está la traza de run, reglas, investigación (pasos MCP y citas), decisiones y rechazos.

## 4. Kill switch de la IA

```text
uv run python scripts/demo.py kill-switch off
```

Con el kill switch apagado, pedir una investigación devuelve "investigación con IA desactivada", y `/metrics` muestra `recon_ai_enabled 0`. La conciliación, los casos, las propuestas sin borrador y las decisiones siguen funcionando. Para reactivarla: `kill-switch on`.

## 5. Operación

- **Métricas y alertas:** `curl http://127.0.0.1:18180/metrics` y `uv run python scripts/ops.py alerts`.
- **Trazas** (opcional, descarga Collector y Jaeger): `uv run python scripts/observability_demo.py` y después Jaeger en `http://127.0.0.1:18186` con `--keep`.
- **Backup y chequeo de restore:** `uv run python scripts/ops.py backup` y `uv run python scripts/ops.py restore-check`.
- **Runbooks:** [docs/runbooks](../runbooks/README.md).

## 6. Recursos y costo

`uv run python scripts/demo.py resources` muestra la memoria y CPU de los contenedores y el tamaño de las imágenes. El costo de la demo en APIs es **0**: no se llama a proveedores de IA externos. El modelo es scripted, y Ollama es opcional y local. Los valores medidos están en el [documento de resultados](results.md).

## 7. Cerrar

```text
docker compose down                     # conserva volúmenes
docker compose --profile smoke down --volumes   # DESTRUCTIVO: borra la base local de esta demo
```

## Qué no demuestra

- Rendimiento productivo ni calidad de un modelo de lenguaje: las salidas de IA son SIMULATED.
- Generalización a datos reales, cumplimiento regulatorio, alta disponibilidad ni seguridad de un despliegue público.

El sistema **no está listo para producción**.
