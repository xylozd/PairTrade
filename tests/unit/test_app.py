"""FastAPI application skeleton.

The `/health` endpoint is what a load balancer, the Docker healthcheck and
the deploy script poll. It has to be honest: a cached 200 from a dead process
is worse than no healthcheck at all.
"""

from __future__ import annotations

import httpx
import pytest


async def test_health_returns_ok(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"]


async def test_health_is_not_cacheable(async_client: httpx.AsyncClient) -> None:
    """A cached health response would mask a dead service."""
    response = await async_client.get("/health")
    assert response.headers.get("cache-control") == "no-store"


async def test_health_only_responds_to_get(async_client: httpx.AsyncClient) -> None:
    response = await async_client.post("/health")
    assert response.status_code == 405


async def test_root_describes_the_service(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "name" in payload


async def test_cors_allows_configured_origin(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get(
        "/health", headers={"Origin": "http://localhost:5173"}
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )


async def test_cors_does_not_allow_unknown_origin(
    async_client: httpx.AsyncClient,
) -> None:
    response = await async_client.get(
        "/health", headers={"Origin": "http://evil.example.com"}
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_cors_preflight_for_configured_origin(
    async_client: httpx.AsyncClient,
) -> None:
    response = await async_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )


async def test_openapi_schema_is_served(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"]
    assert "/health" in schema["paths"]


@pytest.mark.parametrize("path", ["/health", "/"])
async def test_responses_are_json(async_client: httpx.AsyncClient, path: str) -> None:
    response = await async_client.get(path)
    assert response.headers["content-type"].startswith("application/json")
