"""Rate-limit de endpoints de identidad sobre Redis: login (S1.3, C17/C22), registro (S1.4, C14) y,
desde S5.1, confirmación de activación (C3, fuerza bruta del TOTP) y refresh (C7, abuso de
rotación).

Todos comparten el mismo patrón de ventana deslizante (TTL) por intento fallido, sobre dos
primitivas genéricas (`_at_or_above`/`_record_hit`) montadas sobre el script atómico
`_RECORD_FAILURE_LUA` (INCR+EXPIRE en una sola llamada, sin ventana en la que una clave quede sin
TTL y bloquee para siempre):
- login por **(IP + email)**: 5 fallos en 15 min bloquean el 6º intento (aunque la contraseña sea
  buena), sin revelar si era correcta. Un login correcto **resetea** este contador.
- login, tope más grueso por **IP** (20 en 15 min): defensa en profundidad frente al barrido de
  muchos emails distintos desde una misma IP (credential spraying), donde el contador por
  (IP+email) nunca llega a 5.
- confirmación de activación por **token**: cada token de activación tiene su propio contador
  (S5.1 C5), y CUALQUIER intento fallido cuenta, incluido un token desconocido/caducado — si solo
  contaran los códigos incorrectos contra un token real, el propio `429` revelaría que el token
  existe (oráculo de enumeración, invariante §4 de la spec).
- refresh por **IP** (S5.1 C7): no hay una identidad conocida de antemano (el token podría ser
  cualquier cosa), así que el único cubo posible es la IP, igual que el registro; se resetea tras
  una rotación exitosa (igual que login resetea el suyo), para que usuarios legítimos detrás de una
  IP compartida no arrastren fallos ajenos indefinidamente dentro de la ventana.
"""

from __future__ import annotations

import redis.asyncio as aioredis

# Suma un fallo y arma la ventana de forma ATÓMICA (un único EVAL): `INCR` y `EXPIRE` ocurren en la
# misma llamada, así que no hay ventana en la que un corte de Redis/proceso deje la clave sin TTL
# (lo que la bloquearía para siempre, contra la invariante C17/C22: "tras la ventana se vuelve a
# permitir"). Se re-arma el TTL siempre que la clave no tenga expiración (`TTL < 0`, es decir -1),
# así que también auto-cura cualquier clave que quedara sin TTL por la versión no atómica anterior.
# La clave se pasa por KEYS[1] (no por ARGV) para no romper en un despliegue Redis Cluster.
_RECORD_FAILURE_LUA = """
local count = redis.call('INCR', KEYS[1])
if redis.call('TTL', KEYS[1]) < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""

# Mismo contrato que `_RECORD_FAILURE_LUA`, pero para los dos cubos del intake en una sola llamada.
# Redis ejecuta el script de forma atómica, por lo que ningún upload puede observar solo uno de los
# contadores actualizado. Las dos claves se pasan como KEYS para mantener compatibilidad con Redis
# Cluster.
_RECORD_INTAKE_LUA = """
local user_count = redis.call('INCR', KEYS[1])
if redis.call('TTL', KEYS[1]) < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local tenant_count = redis.call('INCR', KEYS[2])
if redis.call('TTL', KEYS[2]) < 0 then
    redis.call('EXPIRE', KEYS[2], ARGV[1])
end
return {user_count, tenant_count}
"""


def _ip_email_key(ip: str, email: str) -> str:
    return f"login:fail:{ip}:{email}"


def _ip_key(ip: str) -> str:
    return f"login:ipfail:{ip}"


def _password_reset_ip_email_key(ip: str, email: str) -> str:
    return f"pwreset:fail:{ip}:{email}"


def _password_reset_ip_key(ip: str) -> str:
    return f"pwreset:ipfail:{ip}"


def _register_ip_key(ip: str) -> str:
    return f"register:ip:{ip}"


def _activation_confirm_key(token: str) -> str:
    return f"activation:confirm:fail:{token}"


def _refresh_key(ip: str) -> str:
    return f"refresh:fail:{ip}"


def _counterparty_draft_key(tenant_id: str, user_id: str) -> str:
    return f"counterparty:draft:{tenant_id}:{user_id}"


def _intake_key(kind: str, tenant_id: str, subject_id: str) -> str:
    return f"intake:{kind}:{tenant_id}:{subject_id}"


async def _at_or_above(redis: aioredis.Redis, key: str, threshold: int) -> bool:
    """True si el contador de `key` ya alcanzó o superó `threshold` dentro de su ventana vigente."""
    count = await redis.get(key)
    return int(count) >= threshold if count is not None else False


async def _record_hit(redis: aioredis.Redis, key: str, window_seconds: int) -> int:
    """Suma un intento a `key` (INCR+EXPIRE atómico) y devuelve el contador resultante."""
    return int(await redis.eval(_RECORD_FAILURE_LUA, 1, key, str(window_seconds)))


async def is_blocked(
    redis: aioredis.Redis, ip: str, email: str, *, max_per_email: int, max_per_ip: int
) -> bool:
    """True si el par (IP+email) o la IP han superado su tope dentro de la ventana."""
    return await _at_or_above(redis, _ip_email_key(ip, email), max_per_email) or await _at_or_above(
        redis, _ip_key(ip), max_per_ip
    )


async def record_failure(
    redis: aioredis.Redis, ip: str, email: str, *, window_seconds: int
) -> None:
    """Suma un fallo a ambos contadores; fija atómicamente el TTL de la ventana al crearlos."""
    for key in (_ip_email_key(ip, email), _ip_key(ip)):
        await _record_hit(redis, key, window_seconds)


async def reset(redis: aioredis.Redis, ip: str, email: str) -> None:
    """Borra el contador por (IP+email) tras un login correcto."""
    await redis.delete(_ip_email_key(ip, email))


async def password_reset_attempt_exceeds(
    redis: aioredis.Redis,
    ip: str,
    email: str,
    *,
    max_per_email: int,
    max_per_ip: int,
    window_seconds: int,
) -> bool:
    """Cuenta una solicitud de "olvidé mi contraseña" y dice si supera el tope de (IP+email) o IP.

    A diferencia del login (que solo cuenta *fallos*), aquí se cuenta CADA solicitud, exista o no la
    cuenta: como la respuesta es genérica y no puede distinguir un email real de uno inventado
    (anti-enumeración), el propio conteo tampoco puede depender de esa distinción -- si solo
    contara cuando la cuenta existe, el tope alcanzado revelaría por sí mismo que el email es real
    (mismo oráculo de enumeración que ya evita `activation_confirm_blocked`).
    """
    email_count = await _record_hit(redis, _password_reset_ip_email_key(ip, email), window_seconds)
    ip_count = await _record_hit(redis, _password_reset_ip_key(ip), window_seconds)
    return email_count > max_per_email or ip_count > max_per_ip


async def register_attempt_exceeds_ip(
    redis: aioredis.Redis, ip: str, *, max_per_ip: int, window_seconds: int
) -> bool:
    """Cuenta un intento de registro por IP (anti-spam, S1.4 C14) y dice si supera el tope.

    Devuelve True cuando el contador de la ventana **supera** `max_per_ip`: el intento que lo
    rebasa recibe 429; los primeros se permiten.
    """
    count = await _record_hit(redis, _register_ip_key(ip), window_seconds)
    return count > max_per_ip


async def activation_confirm_blocked(
    redis: aioredis.Redis, token: str, *, max_attempts: int
) -> bool:
    """True si este token de activación ya agotó su tope de intentos fallidos (S5.1 C3)."""
    return await _at_or_above(redis, _activation_confirm_key(token), max_attempts)


async def record_activation_confirm_failure(
    redis: aioredis.Redis, token: str, *, window_seconds: int
) -> None:
    """Suma un intento fallido (código incorrecto o token inválido) al contador de este token."""
    await _record_hit(redis, _activation_confirm_key(token), window_seconds)


async def refresh_blocked(redis: aioredis.Redis, ip: str, *, max_attempts: int) -> bool:
    """True si esta IP ya agotó su tope de intentos de refresh fallidos (S5.1 C7)."""
    return await _at_or_above(redis, _refresh_key(ip), max_attempts)


async def record_refresh_failure(redis: aioredis.Redis, ip: str, *, window_seconds: int) -> None:
    """Suma un intento de refresh fallido al contador de esta IP."""
    await _record_hit(redis, _refresh_key(ip), window_seconds)


async def reset_refresh(redis: aioredis.Redis, ip: str) -> None:
    """Borra el contador de refresh de esta IP tras una rotación exitosa (auditoría S5.1): evita
    que fallos benignos ajenos (cookies caducadas de otros usuarios en una IP compartida) se
    acumulen indefinidamente contra quien sí consigue refrescar con normalidad."""
    await redis.delete(_refresh_key(ip))


async def draft_counterparty_attempt_exceeds(
    redis: aioredis.Redis, tenant_id: str, user_id: str, *, max_attempts: int, window_seconds: int
) -> bool:
    """Limita la consulta de borrador por identidad, sin castigar a otros usuarios del tenant."""
    count = await _record_hit(redis, _counterparty_draft_key(tenant_id, user_id), window_seconds)
    return count > max_attempts


async def intake_attempt_exceeds(
    redis: aioredis.Redis,
    *,
    kind: str,
    tenant_id: str,
    user_id: str,
    max_per_user: int,
    max_per_tenant: int,
    window_seconds: int,
) -> bool:
    """Limita intake/OCR por usuario y tenant antes de recursos costosos (S6.13)."""
    # Un único EVAL atómico actualiza ambos cubos y evita los viajes de red de dos EVAL separados
    # o de un MULTI/EXEC bajo una oleada de subidas.
    user_count, tenant_count = await redis.eval(
        _RECORD_INTAKE_LUA,
        2,
        _intake_key(kind, tenant_id, f"user:{user_id}"),
        _intake_key(kind, tenant_id, "tenant"),
        str(window_seconds),
    )
    return int(user_count) > max_per_user or int(tenant_count) > max_per_tenant
