# Runbooks (M9)

Procedimientos para el stack local `recon-m0`. Los comandos sólo actúan sobre este proyecto Compose; nunca detienen ni borran contenedores o volúmenes de otros proyectos. Las alertas viven en [infra/observability/alerts.toml](../../infra/observability/alerts.toml) y se evalúan con `uv run python scripts/ops.py alerts`. Sus umbrales son **EXPECTED** (docs/08-risks.md), no SLOs medidos.

| Runbook | Alertas | Ejercitado en |
|---|---|---|
| [Broker o relay caído](broker-down.md) | `OutboxStalled`, `WorkerHeartbeatMissing`, `MetricsSourceDown` | smoke `M9-T05` (fault injection) |
| [Dead letters y replay](dlq-replay.md) | `DeadLetters` | smoke `M9-T05` |
| [Base de datos llena o caída](db-full.md) | `MetricsSourceDown` | smoke M0 (dependencias caídas) |
| [Backup y restore](backup-restore.md) | — | smoke `M9-T06` |
| [Embeddings o investigador no disponibles](embeddings-unavailable.md) | `InvestigatorHeartbeatMissing` | smoke `M9-T05` |
| [Evidencia retirada](evidence-withdrawn.md) | `ToolPermissionRefused` | test de integración de revocación; alerta disparada en vivo en el smoke `M11-T02` |
| [Rollback de ruleset](ruleset-rollback.md) | — | smoke `M11-T03` (`rules/v2` sintético → `rules/v1`) |
| [Backlog humano](human-backlog.md) | `HumanBacklog` | smoke `M11-T02` (recomendación antedatada; dispara y vuelve al estado base) |

Principios: preferir la ruta determinística; ninguna mitigación aprueba casos ni mueve dinero; toda acción manual queda auditada (actor y motivo); no borrar datos para "limpiar" una alerta.
