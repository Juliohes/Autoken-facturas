"""Tests de rate-limit: las claves de fallo SIEMPRE quedan con TTL.

Regresión de robustez: `record_failure` fija el TTL de la ventana de forma atómica junto al `INCR`
(un único EVAL). Si la clave quedara sin expiración, ese (IP+email) o esa IP quedaría bloqueado
indefinidamente, contra la invariante C17/C22 ("tras la ventana se vuelve a permitir").
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as aioredis

from identity import ratelimit
from tests.conftest import _assert_test_redis


@pytest.fixture
async def redis_client() -> AsyncIterator[aioredis.Redis]:
    """Cliente Redis contra el índice de test, vaciado antes y después (aislado de otros casos)."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/15")
    _assert_test_redis(url)  # nunca vaciar un Redis compartido (mismo guard que `authapi`)
    client: aioredis.Redis = aioredis.from_url(url, decode_responses=True)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


async def test_record_failure_arma_ttl_en_ambas_claves(redis_client: aioredis.Redis) -> None:
    """Tras un fallo, las dos claves (IP+email e IP) tienen TTL > 0: ninguna queda sin expirar."""
    ip, email, window = "203.0.113.5", "ana@ilex.es", 900
    await ratelimit.record_failure(redis_client, ip, email, window_seconds=window)

    email_ttl = await redis_client.ttl(ratelimit._ip_email_key(ip, email))
    ip_ttl = await redis_client.ttl(ratelimit._ip_key(ip))
    # `TTL` devuelve -1 (sin expiración) o -2 (inexistente) en caso de bug; exigimos un TTL vivo
    # dentro de la ventana pedida.
    assert 0 < email_ttl <= window
    assert 0 < ip_ttl <= window


async def test_record_failure_repetido_conserva_el_ttl(redis_client: aioredis.Redis) -> None:
    """Sumar varios fallos mantiene la clave con TTL vivo (no se queda nunca sin expiración)."""
    ip, email, window = "203.0.113.9", "leo@ilex.es", 900
    for _ in range(3):
        await ratelimit.record_failure(redis_client, ip, email, window_seconds=window)

    assert await redis_client.get(ratelimit._ip_email_key(ip, email)) == "3"
    assert await redis_client.ttl(ratelimit._ip_email_key(ip, email)) > 0
    assert await redis_client.ttl(ratelimit._ip_key(ip)) > 0


async def test_intake_actualiza_los_dos_cubos_atomicos(redis_client: aioredis.Redis) -> None:
    """El límite de intake actualiza usuario y tenant, y ambos contadores expiran juntos."""
    tenant_id, user_id, window = "tenant-ratelimit", "user-ratelimit", 900

    first = await ratelimit.intake_attempt_exceeds(
        redis_client,
        kind="upload",
        tenant_id=tenant_id,
        user_id=user_id,
        max_per_user=1,
        max_per_tenant=2,
        window_seconds=window,
    )
    second = await ratelimit.intake_attempt_exceeds(
        redis_client,
        kind="upload",
        tenant_id=tenant_id,
        user_id=user_id,
        max_per_user=1,
        max_per_tenant=2,
        window_seconds=window,
    )

    assert first is False
    assert second is True
    assert await redis_client.get(
        ratelimit._intake_key("upload", tenant_id, f"user:{user_id}")
    ) == "2"
    assert await redis_client.get(ratelimit._intake_key("upload", tenant_id, "tenant")) == "2"
    assert await redis_client.ttl(
        ratelimit._intake_key("upload", tenant_id, f"user:{user_id}")
    ) > 0
    assert await redis_client.ttl(ratelimit._intake_key("upload", tenant_id, "tenant")) > 0
