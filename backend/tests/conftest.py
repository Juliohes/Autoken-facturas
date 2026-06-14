"""Fixtures comunes de los tests del backend."""

from collections.abc import AsyncIterator

import httpx
import pytest

from main import app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente HTTP async contra la app FastAPI mediante transporte ASGI."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
