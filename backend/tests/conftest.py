"""Fixtures comunes de los tests del backend."""

import os
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx
import pytest

# Mismo hallazgo que _TEST_MINIO_DEFAULTS más abajo, pero tiene que aplicarse ANTES del `import
# main` de la línea siguiente: `main.py` llama a `get_settings()` (cacheada) al definir `app` a
# nivel de módulo, así que si el `.env` real de esta VPS ya trae `SMTP_HOST` puesto (despliegue
# real en el mismo checkout, 2026-09-03), la primera vez que cualquier test importa `main` deja
# cacheado un `Settings` con SMTP real -- y con él, `notifications.get_notifier()` (singleton de
# proceso) construye un `SmtpNotifier` en vez del `RecordingNotifier` que casi toda la suite da por
# hecho (`.reset()`, `.messages`). `setdefault` en una variable de entorno de verdad SÍ gana al
# `.env` del fichero (pydantic-settings), a diferencia de `monkeypatch.delenv` sobre una clave que
# nunca estuvo en `os.environ` para empezar.
os.environ.setdefault("SMTP_HOST", "")

from main import app  # noqa: E402 (después del setdefault de SMTP_HOST, a propósito)

_LOCAL_REDIS_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "redis"})

# Credenciales de test de MinIO (mismas que `docker-compose.yml` deja por defecto para dev/CI: ver
# `docs/runbooks/tests-locales-vps-b.md` para el hallazgo real que motivó esto, 2026-07-28). Se
# aplican con `setdefault` (mismo criterio que `REDIS_URL` más abajo): `pydantic-settings` lee
# `MINIO_ENDPOINT`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` tanto de variables de entorno reales como
# del `.env` del proyecto (`shared.config.Settings`, `env_file=...`) — y una variable de entorno YA
# presente en el proceso gana siempre a lo que diga ese fichero. En esta VPS concreta (dev/test Y
# despliegue real en el mismo checkout) el `.env` real trae sus propias credenciales de MinIO de
# producción; sin fijar aquí un valor de test ANTES de que `Settings` lo resuelva, los tests
# intentaban escribir contra ese MinIO real (y fallaban, al no ser alcanzable desde fuera de la red
# de Docker del despliegue) en vez de usar el MinIO de test local.
_TEST_MINIO_DEFAULTS = {
    "MINIO_ENDPOINT": "localhost:9000",
    "MINIO_ACCESS_KEY": "minioadmin",
    "MINIO_SECRET_KEY": "minioadmin",
}


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
    prev_minio = {var: os.environ.get(var) for var in _TEST_MINIO_DEFAULTS}
    os.environ["DATABASE_URL"] = dsns["app_async"]
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    for var, default in _TEST_MINIO_DEFAULTS.items():
        os.environ.setdefault(var, default)
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
        restores = [("DATABASE_URL", prev_db), ("REDIS_URL", prev_redis), *prev_minio.items()]
        for var, prev in restores:
            if prev is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = prev
        config.get_settings.cache_clear()
