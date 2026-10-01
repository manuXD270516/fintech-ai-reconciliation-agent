# Resultados de la demo (M10)

Resultados sanitizados de lo que el repositorio demuestra al 2026-10-01. Todo se ejecutó en local, sobre datos sintéticos, con Docker Compose en Windows 11. No se usó CI remoto: GitHub Actions está bloqueado por facturación. Tampoco se usaron APIs pagas ni recursos en la nube. El documento no contiene rutas personales, hosts, tokens ni secretos; los pasos `policy` y `secrets` del gate lo verifican.

**Etiquetas:**
- **MEASURED:** medido aquí, sobre datos sintéticos.
- **SIMULATED:** salida del proveedor de modelo scripted, que es determinístico y no es un LLM.
- **EXPECTED:** objetivo de diseño, no medido.

## Qué funciona (verificado por el gate local)

| Capacidad | Evidencia | Etiqueta |
|---|---|---|
| Conciliación determinística `rules/v1` sobre 1210 pagos en 121 familias: accuracy 1.0 (IC 95 % 0.9968–1.0), 0 falsos EXACT; holdout de 280 pagos con accuracy 1.0 | [evaluation-framework](../../openspec/changes/archive/2026-10-01-evaluation-framework/evidence/README.md) | MEASURED (datos regulares por diseño; no prueba generalización) |
| Ingestion idempotente, cuarentena, outbox/inbox y dead letters | [deterministic-reconciliation](../../openspec/changes/archive/2026-10-01-deterministic-reconciliation/evidence/README.md) | MEASURED |
| Retrieval híbrido, holdout: precision@5 0.231, recall@5 0.923, abstención correcta 0.50 (IC 0.15–0.85), 0 violaciones de ACL | [hybrid-knowledge-retrieval](../../openspec/changes/archive/2026-10-01-hybrid-knowledge-retrieval/evidence/README.md) | MEASURED, **por debajo** de varios objetivos EXPECTED |
| Servidor MCP de sólo lectura: 0 tools prohibidas expuestas o invocables, 0 fugas entre tenants | [read-only-mcp](../../openspec/changes/archive/2026-10-01-read-only-mcp/evidence/README.md) | MEASURED |
| Investigación acotada: 8 escenarios adversariales × 3 con el estado esperado, 0 hechos sin soporte, 0 violaciones de presupuesto | [bounded-investigation](../../openspec/changes/archive/2026-10-01-bounded-investigation/evidence/README.md) | **SIMULATED**: mide guardas y contratos, no la calidad de un modelo |
| Aprobación humana: 576 intentos contra un oráculo independiente; 574 inválidos bloqueados y 0 autoaprobaciones | [review-and-human-approval](../../openspec/changes/archive/2026-10-01-review-and-human-approval/evidence/README.md) | MEASURED |
| Dashboard: E2E analista → supervisora → auditor, con decisión por teclado y 0 violaciones axe serias o críticas | [investigation-dashboard](../../openspec/changes/archive/2026-10-01-investigation-dashboard/evidence/README.md) | MEASURED (navegador headless) |
| Observabilidad: una traza que cruza 4 servicios; alertas disparadas por fallas inyectadas; recuperación exacta; replay idempotente; restore con digest del audit trail | [observability-security](../../openspec/changes/archive/2026-10-01-observability-security/evidence/README.md) | MEASURED |
| Demo: sesiones aisladas por tenant; con el kill switch de IA apagado, el flujo humano completo sigue funcionando | [public-demo](../../openspec/changes/archive/2026-10-01-public-demo/evidence/README.md) | MEASURED |

## Costos y recursos

- **APIs:** 0. Los gates, el smoke y la demo usan el proveedor scripted; las credenciales de IA se eliminan del entorno del gate.
- **Recursos** (una muestra local, `scripts/demo.py resources`): unos 265 MiB de RAM entre los 5 contenedores en reposo (api 70, investigator 77, worker 47, postgres 45 y nats 26 MiB). Imágenes: api 330 MB, pgvector 647 MB y nats 41 MB. Los perfiles opcionales (Ollama, Collector y Jaeger) no están incluidos.
- **Smoke completo:** unos 5 minutos en esta máquina. No es un benchmark.

## Límites visibles

- Las salidas de IA son **SIMULATED**. Ollama local es opcional, no se evaluó y nunca forma parte del gate.
- Los embeddings son de hashing (no semánticos) y el retrieval no alcanza varios objetivos EXPECTED.
- La autenticación usa JWT de desarrollo y la sesión del dashboard se basa en un token pegado a mano. **No es apto para un despliegue público.**
- Revisión de seguridad interna con hallazgos abiertos, entre ellos `/metrics` y Jaeger sin autenticación, falta de rate limiting HTTP y ningún escaneo de vulnerabilidades de dependencias ([security-review](../security-review.md)).
- Sin HA, PITR ni TLS interno. Aprobar sólo registra la decisión y **nunca mueve dinero**.

## Decisiones pendientes del propietario (antes de publicar)

1. **Licencia del repositorio.** No hay `LICENSE`. El inventario de 314 dependencias no encontró licencias GPL/AGPL ni desconocidas; sí hay 19 con copyleft débil (LGPL/MPL), usadas sin modificar ([license-inventory.json](../../openspec/changes/archive/2026-10-01-public-demo/evidence/license-inventory.json)).
2. **Historia git.** Los logs de evidencia de M0/M1 contenían la ruta del perfil de usuario local. Se redactaron en el árbol actual, pero siguen en commits anteriores. Publicar el repositorio tal cual las expondría; reescribir la historia es una decisión del propietario y no se hizo.
3. **Escaneo de secretos.** El de este repo es heurístico (0 hallazgos en todos los commits). Se recomienda ejecutar gitleaks o trufflehog antes de hacerlo público.
4. **Push, PRs y CI.** Los hitos M2–M10 están integrados en `main` sólo de forma local. El CI remoto nunca se ejecutó por el bloqueo de facturación.
