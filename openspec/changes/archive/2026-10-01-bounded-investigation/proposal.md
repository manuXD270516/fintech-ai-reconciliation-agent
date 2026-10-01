## Why

Algunas excepciones de conciliación (diferencias enlazadas, candidatos ambiguos, estados desconocidos, posibles duplicados) necesitan contexto que las reglas no tienen. M5 agrega un agente de investigación acotado que reúne evidencia por el límite MCP de M4 y redacta un borrador con hechos, inferencias e hipótesis separados, sin ningún efecto operativo. El valor está en que cada afirmación queda verificada por código y cada límite (tools, tokens, tiempo, permisos) se impone fuera del modelo.

## What Changes

- **Paquete `recon_agents`:** routing determinístico (exactos, espera y faltantes no invocan modelo), plan por plantilla según el motivo más pasos propuestos por el modelo que pasan una política (sólo catálogo de lectura, IDs del caso, proveedor del caso, presupuesto), ejecución por el cliente MCP real, fase de evidencia determinística y borrador con el contrato de docs/04.
- **Máquina de estados persistida** (D05): `REQUESTED → PLANNED → EXECUTED → DRAFTED | ABSTAINED | ESCALATED | FAILED` o `NOT_NEEDED`, con checkpoint en cada transición, presupuesto por investigación (6 llamadas MCP, 4 generativas, 16 000 tokens, 60 s) y abstención/escalamiento explícitos.
- **Proveedores de modelo** (D03): interfaz `ModelProvider`; `ScriptedProvider` determinístico (SIMULATED) con variantes adversariales para pruebas; `OllamaProvider` local por HTTP (httpx, sin SDK), desactivado por defecto y en un perfil opcional de Compose fijado por digest. Ningún proveedor externo.
- **Persistencia y API:** migración `0005_investigations`, solicitud idempotente por snapshot del caso (sin evidencia nueva no se repite), evento `InvestigationRequested` por outbox, rutas `POST /v1/runs/{run_id}/results/{ordinal}/investigations` (analista) y `GET /v1/investigations/{id}` (lectura).
- **Proceso `investigator`:** consumidor JetStream separado del worker de conciliación, con claim atómico y lease, que lanza `fintech-mcp-server` por stdio con la identidad `svc-investigator` y el rol `recon_mcp`.

## Capabilities

### New Capabilities

- `bounded-investigation`: investigación acotada, auditable y sin efectos de excepciones de conciliación, con evidencia verificada y separación epistemológica de afirmaciones.

### Modified Capabilities

Ninguna en specs vigentes.

## Impact

Paquetes `packages/agents` y `apps/investigator`, dependencias fijadas `httpx==0.28.1` (runtime del agente), migración `0005`, servicio Compose `investigator` y perfil opcional `ollama` (`ollama/ollama:0.35.0@sha256:2a6e…`), dos rutas `/v1` y un paso smoke `M5-T09`.

Decisiones vinculantes: [docs/11-implementation-decisions.md](../../../../docs/11-implementation-decisions.md) (D03, D05); diseño: [docs/04-agents.md](../../../../docs/04-agents.md).

## Non-goals

Reviewer y aprobación humana (M6), calibración de confianza, evaluación con modelo real (requiere Ollama y presupuesto explícito; no forma parte de los gates), UI y cualquier acción operativa.
