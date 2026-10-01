## Context

Implementa la investigación de [docs/04-agents.md](../../../docs/04-agents.md) con D03 (proveedor scripted + Ollama local) y D05 (máquina de estados propia) de [docs/11-implementation-decisions.md](../../../docs/11-implementation-decisions.md), sobre el servidor MCP de M4.

## Goals / Non-Goals

**Goals:** límites impuestos por código, evidencia verificable, separación FACT/INFERENCE/HYPOTHESIS, abstención explícita, ejecución idempotente y pruebas adversariales.

**Non-Goals:** reviewer y aprobación (M6), calibración, calidad de un modelo real.

## Decisions

- **Roles lógicos en un proceso.** Planner = plantilla + una llamada generativa que sólo propone pasos; Executor = cliente MCP; Evidence = fase determinística (`collect` + `verify`); el orquestador impone presupuestos y estados. Sin frameworks de agentes.
- **Proveedor scripted (SIMULATED).** No es un modelo de lenguaje: aplica reglas sobre el contexto estructurado para producir planes y borradores reproducibles. Sus variantes (`injection_follower`, `hallucinator`, `endless_planner`, `malformed`) prueban que los guardas funcionan con un modelo que se porta mal. Toda métrica con él se etiqueta SIMULATED.
- **Ollama.** `OllamaProvider` usa `/api/chat` con `format` = JSON Schema y temperatura 0, por httpx; rechaza URLs fuera de loopback/red interna; reporta tokens del servidor o los marca estimados. Perfil Compose `ollama` opcional fijado por digest; el modelo se descarga bajo demanda. No se ejecuta en gates.
- **Contexto.** Orden de docs/06: autoridad → caso → pregunta → fragmentos envueltos en `<untrusted_document>` → brechas → contrato; recorte con indicador visible a 6000 tokens estimados.
- **Verificación.** Referencias: `tx:<uid>@<rev>`, `status:…`, `calc:difference` (registros) y `doc:<id>@<v>#<chunk>` (documentos). Un FACT necesita una referencia de registro y sus números (≥ 3 dígitos) deben aparecer en los registros citados. Una inferencia de comisión sólo la produce el scripted si la diferencia es exactamente el 1 % documentado.
- **Estados terminales.** Problemas críticos de verificación → `ABSTAINED`; brechas por timeout/dependencia o presupuesto/generación no disponible → `ESCALATED`; resto → `DRAFTED`. Exactos/espera/faltantes → `NOT_NEEDED`.
- **Idempotencia.** `uq_investigation_per_snapshot (tenant, case_ref, input_snapshot_hash)`: repetir sin evidencia nueva devuelve la misma investigación. El hash del snapshot es el mismo en `recon_store` y en `CaseSnapshot` (test).
- **Concurrencia.** `claim` atómico (`UPDATE … WHERE state='REQUESTED' AND NOT claimed` o lease vencido de 600 s) antes de ejecutar; los checkpoints conservan el claim. El rol runtime sólo puede actualizar `state`, `record` y `updated_at`.
- **Separación de procesos.** `apps/investigator` importa el agente; `recon_worker`, `recon_store` y `recon_domain` siguen sin clientes de modelos (test AST de M2).

## Risks / Trade-offs

- El scripted no mide calidad de IA; sólo prueba plumbing, límites y guardas. Afirmar calidad requiere la suite con modelo real (M7/M10) con presupuesto explícito.
- La verificación numérica es conservadora y léxica: puede descartar FACTs correctos redactados con cifras transformadas; se prefiere abstención a hechos sin soporte.
- `investigator` lanza un subprocess MCP por investigación (simple, aislado; costo de arranque aceptable en la demo).
