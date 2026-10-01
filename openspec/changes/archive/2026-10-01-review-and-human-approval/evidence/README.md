# Evidencia — review-and-human-approval (M6)

Ejecutada el 2026-10-01 en Windows 11 (Docker 29.8.1, Compose 5.5.1, linux/amd64), rama `m6-review-and-human-approval` con cambios sin commitear (`dirty: true`). Persistencia, concurrencia, MCP y API son reales (**MEASURED**, locales, sintéticos); las salidas del modelo (borrador y revisión) son **SIMULATED** (`ScriptedProvider`). CI remoto no ejecutado (AC06 de M0).

Archivos:

- [gate-all.log](gate-all.log): `uv run python scripts/gate.py all`, todos PASS; 235 tests unitarios; smoke 17/17.
- [unit-tests.log](unit-tests.log): `pytest -v tests/unit/test_reviewer.py tests/unit/test_approval_policy.py` (19 passed).
- [smoke.json](smoke.json): 80 tests de integración (11 en `test_cases_flow.py`) y el paso `M6-T08`.

## T01

`test_rejecting_reviewer_forces_abstention` (`REJECTED` → `ABSTAINED`, `is_human_approval: false`), `test_model_reviewer_input_is_isolated` (contexto con sólo `case`, `claims`, `citations`, `missing_evidence`, `verification_issues`, `instructions`; sin pasos propuestos ni `<untrusted_document>`), `test_deterministic_review_requires_elements_and_rejects_contradictions`, `test_combination_is_the_most_conservative` y, en `test_agents.py`, la investigación fiel con revisión `SUPPORTED`. Ver [unit-tests.log](unit-tests.log).

## T02

`test_one_reflection_after_actionable_objection_when_budget_allows` (presupuesto 5: dos revisiones, una reflexión, `DRAFTED`) y `test_no_reflection_beyond_the_default_budget_escalates` (presupuesto por defecto: una revisión, `ESCALATED`, motivo "reflection does not fit the generative budget"). Hallazgo documentado en el design: con planificación por modelo el presupuesto EXPECTED de 4 llamadas no deja lugar a la pareja de reflexión. Ver [unit-tests.log](unit-tests.log).

## T03

`tests/unit/test_approval_policy.py`: decisión válida, diez rechazos tipados (incluida la autoaprobación por quien pidió la investigación), la propiedad Hypothesis "nadie aprueba su propia propuesta" (HU01) y las reglas de propuesta y cierre. Ver [unit-tests.log](unit-tests.log).

## T04

`test_reviewed_draft_to_human_decision_and_audit_trail` en [smoke.json](smoke.json): investigación real (MCP por stdio, retrieval real) → caso idempotente → recomendación que adopta el borrador `SUPPORTED` (con citas) → aprobación (versión 2 → 3) → replay con la misma clave devuelve la misma decisión → la misma clave con otro motivo es `idempotency_conflict` → cierre (versión 4) → traza con `case.open`, `recommendation.create`, `decision.record`, `case.close`, `investigation.request`, `investigation.finish`, ruleset `rules/v1`, snapshot hash, pasos y citas de la investigación; exactamente un evento `ApprovalRecorded` cuyo `operational_effect` empieza con "none".

## T05

`test_hu01_self_approval_is_denied_and_audited` (`segregation_of_duties`, caso sigue en `HUMAN_REVIEW`, entrada `decision.denied` del proponente) y `test_hu02_concurrent_decisions_produce_one_transition` (cuatro supervisores en hilos con barrera: una decisión registrada, el resto conflictos). Ver [smoke.json](smoke.json).

## T06

`test_stale_version_and_expired_recommendation` (`version_conflict`, luego `recommendation_expired` para una propuesta de hace 4 días), `test_rc10_newer_run_makes_the_recommendation_obsolete` (run nuevo del lote → `recommendation_obsolete`, estado `OBSOLETE`), `test_unreviewed_or_unneeded_drafts_cannot_be_adopted`. Ver [smoke.json](smoke.json).

## T07

Cinco casos de `test_runtime_role_cannot_rewrite_decisions` (`InsufficientPrivilege`) y `test_schema_matches_sqlalchemy_metadata` sin drift con `0006_cases`. Ver [smoke.json](smoke.json).

## T08

Paso smoke `M6-T08` desde el host por HTTP: caso 201; recomendación 201 que adopta el borrador del paso `M5-T09`; el mismo sujeto con roles analista+supervisor → 403; analista → 403; versión vieja → 409; supervisor aprueba (201, `operational_effect: "none: the decision is recorded; no money movement is executed"`); replay → 200 `replayed: true`; la traza del auditor contiene `case.open`, `recommendation.create`, `investigation.request`, `investigation.finish`, `decision.record` y tres `decision.denied` (`role_not_allowed`, `segregation_of_duties`, `version_conflict`); el analista no puede leer la traza (403).

## T09

Gate completo en [gate-all.log](gate-all.log), incluido el catálogo exacto de rutas.

Complemento de T04/T08 (lectura auditada): [audit-read-check.txt](audit-read-check.txt) muestra entradas `case.audit_read` escritas por el auditor de los tests de integración (`auditor-1`) y por el del smoke (`aud-smoke`), consultadas con el rol runtime en la base local tras el gate.

El archivo del change se verificó con el gate estático posterior a `openspec archive` ([gate-static-post-archive.log](gate-static-post-archive.log): todos PASS, incluida la regla de trazabilidad para changes archivados).
