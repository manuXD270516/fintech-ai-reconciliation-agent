# Evidencia — bounded-investigation (M5)

Ejecutada el 2026-10-01 en Windows 11 (Docker 29.8.1, Compose 5.5.1, linux/amd64), rama `m5-bounded-investigation` con cambios sin commitear (`dirty: true` en el smoke). Plataforma, MCP, retrieval y persistencia son reales (**MEASURED**, locales, datos sintéticos); **las salidas del modelo son SIMULATED** (`ScriptedProvider`, reglas determinísticas, no un modelo de lenguaje). No se llamó a ningún proveedor de IA ni a Ollama. CI remoto no ejecutado (AC06 de M0).

Archivos:

- [gate-all.log](gate-all.log): `uv run python scripts/gate.py all`, todos PASS; 216 tests unitarios; smoke 16/16.
- [unit-tests.log](unit-tests.log): `pytest -v tests/unit/test_agents.py` (20 passed).
- [smoke.json](smoke.json): 69 tests de integración (7 en `test_investigation_flow.py`) y el paso `M5-T09`.

## T01

`test_routing_requires_an_explicit_reason` (7 casos) y `test_exact_match_costs_zero_model_and_tool_calls` (`NOT_NEEDED`, `provider.calls == []`, `tool_calls == 0`). Ver [unit-tests.log](unit-tests.log).

## T02

`test_ag02_injected_instructions_never_reach_tools_or_actions`: `approve_resolution` y `fetch_url` rechazados (`tool_not_in_read_catalog`), sólo tools del catálogo ejecutadas, el servidor sigue listando exactamente las seis tools, advertencias de contenido no confiable en el borrador. `test_endless_planning_is_capped_by_the_tool_budget`: 6 llamadas y 9 rechazos por presupuesto. Ver [unit-tests.log](unit-tests.log).

## T03

`test_faithful_investigation_separates_facts_inferences_and_hypotheses`: `DRAFTED`, hechos con 10000, 9900 y −100, el incidente INC-0815 sólo como HYPOTHESIS (AG01), todas las referencias de los hechos presentes en `citations`, `uncalibrated`, `SIMULATED`, `operational_effect: none`, `REQUEST_PROVIDER_INFO`, ≤ 6 llamadas MCP, 2 generativas, tokens bajo el máximo y marcados como estimados, checkpoints `REQUESTED → PLANNED → EXECUTED → DRAFTED`. Ver [unit-tests.log](unit-tests.log).

## T04

`test_hallucinated_facts_are_rejected_and_force_abstention` ("FACT backed only by documents" y "unresolvable citation"; ni el reembolso inventado ni el incidente quedan como hechos), `test_malformed_model_output_never_becomes_a_draft_claim` y, en T02, `APPROVE_RESOLUTION` reemplazado por `HUMAN_REVIEW`. Ver [unit-tests.log](unit-tests.log).

## T05

`test_ag03_tool_timeouts_become_gaps_and_escalation` (todas las llamadas `TIMEOUT`, brechas en `missing_evidence`), `test_generative_budget_exhaustion_escalates` (`ESCALATED`, `generative_calls` agotado), `test_context_marks_documents_untrusted_and_respects_budget`. Ver [unit-tests.log](unit-tests.log).

## T06

`test_ollama_provider_speaks_http_and_reports_usage` (`httpx.MockTransport`: temperatura 0, 321/12 tokens reportados, URL externa rechazada), `test_provider_selection_defaults_to_scripted` (proveedor `openai` rechazado), `test_mcp_server_environment_drops_other_credentials`, `test_agent_catalog_mirrors_the_server_catalog`. Ver [unit-tests.log](unit-tests.log).

## T07

En [smoke.json](smoke.json): `test_snapshot_hash_is_shared_by_store_and_agent`; en `test_amount_mismatch_investigation_end_to_end` la segunda solicitud devuelve el mismo ID sin crear otra, el servicio `investigator` y el test compiten por el mismo evento y sólo uno ejecuta (estado final `DRAFTED`, una única auditoría `investigation.finish`, re-ejecución `duplicate`); `test_other_tenant_cannot_read_investigations`; 3 casos de `test_runtime_role_cannot_rewrite_investigation_identity`.

## T08

`test_amount_mismatch_investigation_end_to_end` con el servidor MCP real por stdio (rol `recon_mcp`) y el retrieval híbrido real: hechos con la diferencia −100, hipótesis sin promover, sin inferencia de comisión (−100 no es el 1 % del monto del ledger, la regla documentada), todas las llamadas MCP auditadas bajo `svc-investigator`; `test_exact_result_needs_no_investigation` con presupuesto en cero. Ver [smoke.json](smoke.json).

## T09

Paso smoke `M5-T09` en [smoke.json](smoke.json), desde el host por HTTP: diferencia de importe → `DRAFTED`, 6 llamadas MCP, 2 generativas, ~3353 tokens estimados, `scripted/faithful/v1`, `SIMULATED`, 4 hechos y 1 hipótesis; exacto → `NOT_NEEDED` con 0 llamadas; repetición idempotente (200, mismo ID) y auditor → 403; ambas investigaciones terminaron en 3.71 s (incluye arranque del subprocess MCP).

## T10

Gate completo en [gate-all.log](gate-all.log): incluye el catálogo exacto de rutas (`test_scope.py`) y el test AST que mantiene a `recon_domain`, `recon_store` y `recon_worker` sin clientes de modelos.
