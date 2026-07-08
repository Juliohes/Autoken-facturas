"""Cliente Redis async perezoso (S1.3).

Redis sostiene el rate-limit de login, la rotación del refresh (con detección de reuso) y los tokens
de activación de un solo uso. El cliente se crea de forma perezosa desde `REDIS_URL` y se reutiliza,
igual que el engine de BD (`shared.db`): así no se abre el pool en import-time ni antes del event
loop de los tests. `get_redis` es sustituible/monkeypatchable en pruebas.

Invariante de seguridad (§5 de la spec S1.3): las rutas que dependen de Redis (login, refresh,
activación) **fallan cerrado** si Redis no responde (503), nunca "pasa todo el mundo".
"""

from __future__ import annotations

import redis.asyncio as aioredis

from shared.config import get_settings

# Se reexporta el tipo de error para que las rutas puedan capturar "Redis no disponible" -> 503.
RedisError = aioredis.RedisError

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Devuelve el cliente Redis (perezoso y reutilizado). `decode_responses` -> str al leer.

    Perezoso para no atar el import a `REDIS_URL` ni crear conexiones antes del event loop. En tests
    se libera entre casos con `dispose_redis` para no arrastrar un cliente atado a un loop muerto.
    """
    global _client
    if _client is None:
        _client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def dispose_redis() -> None:
    """Cierra el cliente y su pool (lifespan de la app; tests entre casos)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
