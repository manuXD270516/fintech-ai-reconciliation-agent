# Evidencia — observability-security (M9)

Ejecución local en Windows 11 con Docker Desktop, el 2026-10-01, sobre la rama `m9-observability-security`: base `6cba5aa` más la actualización del README y del change, sin confirmar (`dirty=true`). No es CI remoto: GitHub Actions no ejecuta jobs por el bloqueo de facturación, así que AC06 de M0 sigue PENDING. Todos los datos son sintéticos y no se usó ningún proveedor de IA externo.

| Archivo | Contenido |
|---|---|
| [gate-all.log](gate-all.log) | `scripts/gate.py all`. Los 12 pasos en PASS: test (296 unit), secrets y smoke (23/23, con 86 tests de integración) |
| [smoke.json](smoke.json) | Reporte del smoke con `M9-T04`, `M9-T05` (×2) y `M9-T06` |
| [tracing-demo.json](tracing-demo.json) | `scripts/observability_demo.py` con el perfil `observability` (Collector 0.162.0 y Jaeger 2.21.0) |
| [secret-scan.json](secret-scan.json) | `scripts/secret_scan.py` sobre toda la historia: 0 hallazgos |

## Por criterio

- **AC01:** traza `898e79a4…` con 22 spans de `recon-api` (POST de investigación), `recon-worker` (`publish InvestigationRequested`), `recon-investigator` (proceso, `model.generate plan/draft/review`, clientes MCP) y `fintech-mcp-server` (`tools/call …`). Ninguno de los 88 spans revisados tiene atributos prohibidos (tracing-demo.json). Al terminar, el demo recrea los servicios sin exportador. Tests unitarios: el `traceparent` hace ida y vuelta y la telemetría está apagada por defecto.
- **AC02:** `M9-T04` encontró 23 series y sólo estas etiquetas: `le`, `match_status`, `method`, `outcome`, `reason`, `result`, `route`, `service`, `source`, `state`, `status`, `status_class`, `tool`. No hay IDs en las rutas ni secretos en el cuerpo. Los tests unitarios cubren plantillas de ruta, `unmatched` y fuentes caídas con `up 0` sin que falle el scrape. La integración `test_observability_store.py` usa un snapshot real.
- **AC03:**
  - Las reglas válidas enlazan runbooks existentes (test unitario) y hay un test parametrizado por falla.
  - En vivo (`M9-T05`): `MetricsSourceDown` disparó a los 2 s, `OutboxStalled` a los 62,4 s y `WorkerHeartbeatMissing` a los 2 s; las tres se limpiaron después de la recuperación.
  - `DeadLetters` disparó con el mensaje veneno y se limpió después del triage.
  - `HumanBacklog` y `ToolPermissionRefused` sólo tienen verificación unitaria: un backlog de 24 h no se reproduce en el smoke.
- **AC04:** con NATS y el worker detenidos, el run quedó en `requested`. Tras la recuperación se completó una sola vez: 7 filas que coinciden con los conteos y un único run en el lote. Un re-run dio el mismo snapshot y los mismos conteos. En el DLQ:
  - el replay se negó a re-publicar el veneno (`not_replayable`);
  - el veneno se descartó y la entrega agotada se re-publicó;
  - una segunda copia del mismo evento no cambió los efectos (1 artefacto, 1 observación);
  - quedaron auditadas `dlq.discard`, `dlq.replay` y `dlq.replay` con el operador.
- **AC05:** `M9-T06` hizo un dump de 1,35 MB (27 374 filas) en 1,48 s y el restore en 0,93 s. Conteos y digest del audit trail coinciden y no hubo filas escritas después del backup. Es MEASURED en una sola ejecución local y no predice tiempos con datos reales.
- **AC06:** 8 runbooks en `docs/runbooks/`. Los comandos de alertas, DLQ y backup se ejecutan en los drills. La revocación se ejercita en `test_revoke_command_of_the_runbook_is_audited` (integración). El rollback de ruleset está documentado como **no ejercitado** porque sólo existe `rules/v1`.
- **AC07:** el paso `secrets` escaneó 34 commits sin hallazgos (los canarios por patrón están en tests unitarios). `test_access_matrix.py` cubre 18 rutas × 5 roles, con 401 y 403 antes del almacenamiento. Los grants mínimos de `service_heartbeats` y `outbox` se verifican en integración. Revisión: `docs/security-review.md`, con hallazgos S1–S7 abiertos o aceptados.
- **AC08:** gate-all.log en PASS, con los drills de M9 dentro del smoke.

## Límites

- Las alertas se evalúan de forma instantánea con un script: no hay Prometheus, Alertmanager ni paging.
- El escáner de secretos es heurístico; no se ejecutó gitleaks.
- No se ejecutó un escaneo de vulnerabilidades de dependencias.
- `/metrics` y la UI de Jaeger no tienen autenticación (sólo loopback).
