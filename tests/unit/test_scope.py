"""T12 (M0) + M2 T06: the API exposes exactly the declared route catalog.

M0 allowed only health and docs. M2 (`deterministic-reconciliation`) adds the versioned
ingestion and reconciliation routes below; any other route, method or payment/agent
operation still fails this test.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from fastapi.routing import APIRoute
from starlette.routing import BaseRoute, Route

from .conftest import Harness

HEALTH = {
    ("/health/live", "GET"),
    ("/health/ready", "GET"),
}
M2_RECONCILIATION = {
    ("/v1/artifacts", "POST"),
    ("/v1/batches", "POST"),
    ("/v1/batches/{batch_id}", "GET"),
    ("/v1/batches/{batch_id}/sources/{source}/complete", "POST"),
    ("/v1/batches/{batch_id}/runs", "POST"),
    ("/v1/runs/{run_id}", "GET"),
    ("/v1/runs/{run_id}/results", "GET"),
}
CATALOG = HEALTH | M2_RECONCILIATION
DOCS = {"/openapi.json", "/docs", "/docs/oauth2-redirect"}
FORBIDDEN_WORDS = ("payment", "refund", "transfer", "payout", "execute", "agent", "approve")


def _flatten(routes: Iterable[BaseRoute]) -> Iterator[BaseRoute]:
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _flatten(included.routes)
        else:
            yield route


def test_route_catalog_is_exactly_declared(harness: Harness) -> None:
    paths = {r.path for r in _flatten(harness.app.routes) if isinstance(r, Route)}
    assert paths == {p for p, _ in CATALOG} | DOCS


def test_route_methods_match_catalog(harness: Harness) -> None:
    api_routes = [r for r in _flatten(harness.app.routes) if isinstance(r, APIRoute)]
    assert {(r.path, m) for r in api_routes for m in (r.methods or ())} == CATALOG


def test_no_money_movement_or_agent_routes(harness: Harness) -> None:
    for path, _ in CATALOG:
        assert not any(word in path for word in FORBIDDEN_WORDS), path


async def test_openapi_documents_only_catalog(harness: Harness) -> None:
    async with harness.client() as client:
        spec = (await client.get("/openapi.json")).json()
    assert set(spec["paths"]) == {p for p, _ in CATALOG}
