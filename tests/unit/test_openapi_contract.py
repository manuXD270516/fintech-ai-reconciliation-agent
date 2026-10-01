"""M8 T01: the web client is generated from the API's current OpenAPI document."""

from __future__ import annotations

from scripts.export_openapi import TARGET, render


def test_committed_openapi_matches_the_application() -> None:
    assert TARGET.read_text(encoding="utf-8") == render(), (
        "apps/web/openapi.json is stale: run `uv run python scripts/export_openapi.py` "
        "and `npm --prefix apps/web run gen:api`"
    )


def test_case_models_are_typed_for_the_client() -> None:
    spec = render()
    for name in ("CaseOut", "RecommendationOut", "DecisionIn", "AuditTrailOut", "ResultPage"):
        assert f'"{name}"' in spec, name
