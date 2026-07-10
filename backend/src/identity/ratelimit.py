"""Rate-limit de login (fuerza bruta) sobre Redis (S1.3, criterios C17 y C22).

Dos contadores con ventana deslizante (TTL) por intento fallido:
- por **(IP + email)**: 5 fallos en 15 min bloquean el 6º intento (aunque la contraseña sea buena),
  sin revelar si era correcta. Un login correcto **resetea** este contador.
- un tope más grueso por **IP** (20 en 15 min): defensa en profundidad frente al barrido de muchos
  emails distintos desde una misma IP (credential spraying), donde el contador por (IP+email) nunca
  llega a 5.
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


def _ip_email_key(ip: str, email: str) -> str:
    return f"login:fail:{ip}:{email}"


def _ip_key(ip: str) -> str:
    return f"login:ipfail:{ip}"


def _register_ip_key(ip: str) -> str:
    return f"register:ip:{ip}"


async def is_blocked(
    redis: aioredis.Redis, ip: str, email: str, *, max_per_email: int, max_per_ip: int
) -> bool:
    """True si el par (IP+email) o la IP han superado su tope dentro de la ventana."""
    per_email = await redis.get(_ip_email_key(ip, email))
    per_ip = await redis.get(_ip_key(ip))
    email_count = int(per_email) if per_email is not None else 0
    ip_count = int(per_ip) if per_ip is not None else 0
    return email_count >= max_per_email or ip_count >= max_per_ip


async def record_failure(
    redis: aioredis.Redis, ip: str, email: str, *, window_seconds: int
) -> None:
    """Suma un fallo a ambos contadores; fija atómicamente el TTL de la ventana al crearlos.

    `INCR` + `EXPIRE` van en un único script Lua para que la clave nunca quede sin TTL (que la
    bloquearía indefinidamente): C17/C22 exige que, pasada la ventana, se vuelva a permitir.
    """
    for key in (_ip_email_key(ip, email), _ip_key(ip)):
        await redis.eval(_RECORD_FAILURE_LUA, 1, key, str(window_seconds))


async def reset(redis: aioredis.Redis, ip: str, email: str) -> None:
    """Borra el contador por (IP+email) tras un login correcto."""
    await redis.delete(_ip_email_key(ip, email))


async def register_attempt_exceeds_ip(
    redis: aioredis.Redis, ip: str, *, max_per_ip: int, window_seconds: int
) -> bool:
    """Cuenta un intento de registro por IP (anti-spam, S1.4 C14) y dice si supera el tope.

    Reutiliza el script atómico `INCR`+`EXPIRE` de S1.3 (la clave nunca queda sin TTL, así que
    pasada la ventana se vuelve a permitir). Devuelve True cuando el contador de la ventana
    **supera** `max_per_ip`: el intento que lo rebasa recibe 429; los primeros se permiten.
    """
    count = await redis.eval(_RECORD_FAILURE_LUA, 1, _register_ip_key(ip), str(window_seconds))
    return int(count) > max_per_ip
