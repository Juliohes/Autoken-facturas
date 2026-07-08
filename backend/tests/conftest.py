"""Fixtures comunes de los tests del backend."""

import os
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx
import pytest

from main import app

_LOCAL_REDIS_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "redis"})


def _assert_test_redis(url: str) -> None:
    """Aborta si `REDIS_URL` no parece de test, ANTES de vaciarla con `flushdb` (footgun F5).

    `flushdb` borra TODO el índice de Redis. Si `REDIS_URL` viniera apuntando a un Redis compartido
    (host remoto e índice 0 por defecto), este fixture lo vaciaría. Se exige un índice dedicado de
    test (path != /0) o un host local; en otro caso se detiene con un mensaje claro.
    """
    parsed = urlparse(url)
    db_index = parsed.path.lstrip("/") or "0"
    is_local = (parsed.hostname or "") in _LOCAL_REDIS_HOSTS
    if not is_local and db_index == "0":
        raise RuntimeError(
            f"REDIS_URL={url!r} no parece de test: usa un índice de BD dedicado (p. ej. /15) o un "
            "Redis local antes de que el fixture `authapi` ejecute flushdb()."
        )


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente HTTP async contra la app FastAPI mediante transporte ASGI."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authapi() -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, str]]]:
    """App cableada a una BD de test real (rol runtime) + Redis, con cliente HTTP.

    Devuelve `(client, dsns)`. Usuarios/tenants se siembran como superusuario con los helpers de
    `tests._dbtest`; la app se conecta como el rol runtime. `REDIS_URL` apunta a un índice de test
    para el rate-limit y la rotación del refresh (el flujo verde necesita Redis, igual que
    Postgres). Reutiliza el patrón de la fixture `api` de S1.2.
    """
    from shared import config
    from shared import db as db_module
    from shared import redis as redis_module
    from tests._dbtest import provision_test_db

    dsns = await provision_test_db()
    prev_db = os.environ.get("DATABASE_URL")
    prev_redis = os.environ.get("REDIS_URL")
    os.environ["DATABASE_URL"] = dsns["app_async"]
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    config.get_settings.cache_clear()
    await db_module.dispose_engine()

    # Aísla Redis por test: cada caso corre en su propio event loop, así que se descarta el cliente
    # cacheado (atado al loop anterior) y se vacía el índice de test para no arrastrar contadores de
    # rate-limit ni familias de refresh entre casos (spec S1.3 §7: se limpia la clave entre tests).
    await redis_module.dispose_redis()
    _assert_test_redis(os.environ["REDIS_URL"])
    await redis_module.get_redis().flushdb()

    from main import create_app

    # raise_app_exceptions=False: una excepción no controlada se convierte en 500 (como en prod).
    transport = httpx.ASGITransport(app=create_app(), raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, dsns
    finally:
        await db_module.dispose_engine()
        await redis_module.dispose_redis()
        for var, prev in (("DATABASE_URL", prev_db), ("REDIS_URL", prev_redis)):
            if prev is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = prev
        config.get_settings.cache_clear()
