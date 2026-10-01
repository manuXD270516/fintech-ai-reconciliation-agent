# Estrategia de pruebas — M5

Unitarias con cliente MCP real en memoria sobre el backend de fixture y proveedores scripted (fieles y adversariales); integración con PostgreSQL, el servidor MCP por stdio con el rol `recon_mcp` y el retrieval híbrido reales; E2E HTTP con el servicio `investigator`. Las salidas del modelo son SIMULATED.

| ID | Nivel / caso | Método y oráculo |
|---|---|---|
| T01 | Routing | Tabla de siete casos (exacto, espera, faltante, probable, error de proceso, duplicado, diferencia) y exacto con cero llamadas de modelo y tools (`tests/unit/test_agents.py`) |
| T02 | Política de plan | AG02: `approve_resolution` y `fetch_url` rechazados, sólo tools del catálogo ejecutadas, catálogo del servidor intacto; planificador sin fin limitado a 6 llamadas (mismo archivo) |
| T03 | Evidencia y borrador | Investigación fiel `DRAFTED`: hechos con 10000/9900/−100, AG01 incidente como HYPOTHESIS, citas resolubles, `uncalibrated`, `SIMULATED`, `operational_effect: none`, checkpoints en orden (mismo archivo) |
| T04 | Verificación adversarial | Alucinación (FACT sólo con documento y cita inventada) → descartada y `ABSTAINED`; salida malformada → `ABSTAINED`; siguiente paso no permitido → `HUMAN_REVIEW` (mismo archivo) |
| T05 | Límites y fallas | AG03: timeouts MCP → brechas y escalamiento; presupuesto generativo agotado → `ESCALATED`; contexto con documentos `<untrusted_document>` recortado al presupuesto (mismo archivo) |
| T06 | Proveedores | Ollama por `httpx.MockTransport` (payload con temperatura 0, uso de tokens reportado, URL externa rechazada); selección por entorno: scripted por defecto, proveedor externo rechazado; entorno del subprocess MCP sin credenciales ajenas (mismo archivo) |
| T07 | Persistencia | Hash de snapshot compartido store/agente; solicitud idempotente; carrera con el servicio `investigator` resuelta por claim (un solo `DRAFTED`, re-ejecución `duplicate`); otro tenant sin acceso; rol runtime sin DELETE ni cambio de identidad (`tests/integration/test_investigation_flow.py`) |
| T08 | Integración real | Mismo archivo: MCP por stdio + retrieval real + scripted: diferencia −100 en hechos, incidentes sólo como hipótesis, sin inferencia de comisión (−100 no es 1 %), llamadas MCP auditadas por `svc-investigator`; exacto `NOT_NEEDED` con presupuesto en cero |
| T09 | E2E HTTP | Smoke `M5-T09`: `POST …/investigations` (202, repetición 200 idempotente, auditor 403) → outbox → JetStream → `investigator` → MCP → `GET /v1/investigations/{id}`: diferencia `DRAFTED` `SIMULATED`, exacto `NOT_NEEDED` con cero llamadas generativas |
| T10 | Gate | `scripts/gate.py all`, catálogo de rutas y AST sin modelos en el motor determinístico |

## Ejecución y evidencias

`uv run python scripts/gate.py all`. Evidencia en [evidence/](evidence/README.md). Ninguna prueba llama a proveedores externos ni requiere Ollama.

## Stop condition

M5 no crea recomendaciones aprobables, reviewer ni decisiones humanas.
