"""Shared test fixtures.

Starlette 1.9 deprecated `starlette.testclient.TestClient` in favour of
driving the ASGI app directly with `httpx.ASGITransport`. We use the latter:
it keeps the already-pinned `httpx` as the only HTTP client and avoids the
deprecated import path entirely.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest


@pytest.fixture
async def async_client() -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client bound to the ASGI app under test."""
    from app import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client
