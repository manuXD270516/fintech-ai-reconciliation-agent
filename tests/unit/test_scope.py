"""T12: the M0 API exposes only health and technical API documentation."""

from __future__ import annotations

from fastapi.routing import APIRoute
from starlette.routing import Route

from .conftest import Harness

ALLOWED_PATHS = {
    "/health/live",
    "/health/ready",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
}


def test_route_catalog_is_health_and_docs_only(harness: Harness) -> None:
    paths = {route.path for route in harness.app.routes if isinstance(route, Route)}
    assert paths == ALLOWED_PATHS


def test_business_routes_are_get_only_health(harness: Harness) -> None:
    api_routes = [route for route in harness.app.routes if isinstance(route, APIRoute)]
    assert {(r.path, frozenset(r.methods or ())) for r in api_routes} == {
        ("/health/live", frozenset({"GET"})),
        ("/health/ready", frozenset({"GET"})),
    }


async def test_openapi_documents_only_health(harness: Harness) -> None:
    async with harness.client() as client:
        spec = (await client.get("/openapi.json")).json()
    assert set(spec["paths"]) == {"/health/live", "/health/ready"}
