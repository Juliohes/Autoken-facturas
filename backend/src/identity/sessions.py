"""Refresh token rotativo con detección de reuso, sobre Redis (S1.3, ADR-0012).

El refresh es una credencial opaca de vida larga (cookie httpOnly) cuyo único uso es obtener un
access nuevo. Cada uso lo **rota**: emite uno nuevo e invalida el anterior. La cadena de refreshes
de una misma sesión es la "familia". Si aparece un refresh ya rotado (señal de robo), se **revoca la
familia entera**, obligando a re-login (el dueño lo detecta al siguiente uso).

Modelo en Redis (todas las claves con TTL = vida del refresh):
- `refresh:tok:{token}`   -> JSON {family, user_id, tenant_id, role, epoch}. El registro del token.
- `refresh:fam:{family}:current` -> el token vigente de la familia (el único aceptable).
- `refresh:fam:{family}:revoked`  -> marca de familia revocada.
- `refresh:epoch:{user_id}` -> generación vigente de sesiones del usuario (entero, ausente = 0).

El registro del token viejo NO se borra al rotar: así, si se vuelve a presentar (token != current),
se distingue el reuso (revoca familia) de un token desconocido (401 a secas).

La rotación se ejecuta como **un script Lua atómico** (F1): leer el registro, comprobar
revocación/reuso/subdominio y fijar el nuevo token vigente ocurren sin ventana TOCTOU entre ellos.
El nuevo token se genera fuera (CSPRNG de Python) y se pasa al script.

**Revocación de TODAS las sesiones de un usuario** (`revoke_all_sessions`, PROMPT-AUTOFACTU-AUTH-
COMPLETO bloque 1: cambiar la contraseña por "olvidé mi contraseña" cierra las sesiones abiertas).
No hay un índice inverso user_id->familias (harían falta escrituras extra en cada login para
mantenerlo), así que se usa el patrón de "generación" (epoch), habitual para este problema: cada
token lleva grabada la generación vigente del usuario en el momento de emitirse; `rotate_refresh_
token` la compara contra la generación ACTUAL antes de aceptar rotar. Subir la generación (un
simple INCR) invalida de golpe todos los refresh emitidos antes, sin tener que enumerarlos ni
tocarlos uno a uno.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass

import redis.asyncio as aioredis

# Prefijos de las claves; deben coincidir con los que construye el script Lua.
_TOK_PREFIX = "refresh:tok:"
_FAM_PREFIX = "refresh:fam:"
_EPOCH_PREFIX = "refresh:epoch:"


# Rotación atómica. Devuelve un array cuyo primer elemento es el resultado:
#   {'ok', <registro json>}  -> rotado; el registro (con family/user_id/tenant_id/role/epoch) va
#                                detrás.
#   {'invalid'}              -> token desconocido, caducado, familia ya revocada, o de una
#                                generación anterior a la vigente (revocación global, más abajo).
#   {'reuse'}                -> token ya rotado (robo): además revoca la familia entera.
#   {'tenant_mismatch'}      -> el subdominio no casa con el tenant de la familia (F2): no rota.
# ARGV: token actual, token nuevo, tenant esperado ('' = sin tenant / platform_admin), ttl.
# Los prefijos van como placeholders (`__TOK__`/`__FAM__`/`__EPOCH__`) y se sustituyen al cargar,
# para no reescribir el prefijo dentro del script Lua y mantener una única fuente de verdad.
_ROTATE_LUA = (
    """
local tok_key = '__TOK__' .. ARGV[1]
local raw = redis.call('GET', tok_key)
if not raw then return {'invalid'} end
local data = cjson.decode(raw)
local fam = '__FAM__' .. data['family']
if redis.call('GET', fam .. ':revoked') then return {'invalid'} end
local current = redis.call('GET', fam .. ':current')
if current ~= ARGV[1] then
    redis.call('SET', fam .. ':revoked', '1', 'EX', ARGV[4])
    return {'reuse'}
end
local tok_tenant = data['tenant_id']
if tok_tenant == nil or tok_tenant == cjson.null then tok_tenant = '' end
if tok_tenant ~= ARGV[3] then return {'tenant_mismatch'} end
local token_epoch = data['epoch']
if token_epoch == nil or token_epoch == cjson.null then token_epoch = 0 end
local current_epoch = tonumber(redis.call('GET', '__EPOCH__' .. data['user_id'])) or 0
if token_epoch < current_epoch then return {'invalid'} end
redis.call('SET', '__TOK__' .. ARGV[2], raw, 'EX', ARGV[4])
redis.call('SET', fam .. ':current', ARGV[2], 'EX', ARGV[4])
return {'ok', raw}
""".replace("__TOK__", _TOK_PREFIX)
    .replace("__FAM__", _FAM_PREFIX)
    .replace("__EPOCH__", _EPOCH_PREFIX)
)


@dataclass(frozen=True)
class RotatedSession:
    """Resultado tipado de rotar un refresh: el nuevo token opaco + la identidad de la familia."""

    new_token: str
    user_id: str
    tenant_id: str | None
    role: str


def _tok_key(token: str) -> str:
    return f"{_TOK_PREFIX}{token}"


def _fam_current_key(family: str) -> str:
    return f"{_FAM_PREFIX}{family}:current"


def _epoch_key(user_id: str) -> str:
    return f"{_EPOCH_PREFIX}{user_id}"


async def issue_refresh_token(
    redis: aioredis.Redis,
    *,
    user_id: str,
    tenant_id: str | None,
    role: str,
    ttl_seconds: int,
) -> str:
    """Abre una familia nueva y devuelve su primer refresh token (tras un login correcto).

    Graba la generación (epoch) vigente del usuario en el momento de emitirlo (0 si nunca se ha
    revocado nada): `rotate_refresh_token` la compara contra la vigente en cada rotación, así que
    una `revoke_all_sessions` posterior invalida este token sin tocarlo.
    """
    family = secrets.token_urlsafe(32)
    token = secrets.token_urlsafe(32)
    epoch = int(await redis.get(_epoch_key(user_id)) or 0)
    record = json.dumps(
        {"family": family, "user_id": user_id, "tenant_id": tenant_id, "role": role, "epoch": epoch}
    )
    await redis.set(_tok_key(token), record, ex=ttl_seconds)
    await redis.set(_fam_current_key(family), token, ex=ttl_seconds)
    return token


async def rotate_refresh_token(
    redis: aioredis.Redis,
    token: str,
    *,
    expected_tenant_id: str | None,
    ttl_seconds: int,
) -> RotatedSession | None:
    """Rota un refresh válido a un `RotatedSession`, o `None` si no vale (el llamante -> 401).

    Devuelve `None` cuando el token es desconocido (incluida una cookie ausente: se pasa como
    cadena vacía, que nunca casa con ninguna clave), su familia está revocada, es un token ya
    rotado (reuso: además revoca la familia entera) o el `expected_tenant_id` no casa con el tenant
    de la familia (F2: defensa en profundidad; en ese caso NO se rota ni se revoca, para no
    bloquear al dueño legítimo). Toda la comprobación es atómica (un único script Lua).

    Función PURA sobre el mecanismo de rotación: el rate-limit (S5.1 C7) es una política transversal
    ajena a "qué es rotar un refresh", así que vive en la capa de caso de uso
    (`identity.service.refresh_session`), igual que el login orquesta su propio rate-limit por
    encima de `issue_refresh_token` en vez de dentro (auditoría de arquitectura S5.1).
    """
    new_token = secrets.token_urlsafe(32)
    expected = expected_tenant_id if expected_tenant_id is not None else ""
    result = await redis.eval(_ROTATE_LUA, 0, token, new_token, expected, str(ttl_seconds))
    if not result or result[0] != "ok":
        return None
    data = json.loads(result[1])
    return RotatedSession(
        new_token=new_token,
        user_id=data["user_id"],
        tenant_id=data["tenant_id"],
        role=data["role"],
    )


async def revoke_family(redis: aioredis.Redis, token: str, *, ttl_seconds: int) -> None:
    """Revoca la familia del `token` (logout). Idempotente: si el token no existe, no hace nada."""
    raw = await redis.get(_tok_key(token))
    if raw is None:
        return
    family = json.loads(raw)["family"]
    await redis.set(f"{_FAM_PREFIX}{family}:revoked", "1", ex=ttl_seconds)


async def revoke_all_sessions(redis: aioredis.Redis, user_id: str, *, ttl_seconds: int) -> None:
    """Sube la generación de sesiones del usuario: invalida de golpe TODOS sus refresh vigentes.

    Cambio de contraseña por "olvidé mi contraseña" (PROMPT-AUTOFACTU-AUTH-COMPLETO bloque 1):
    cualquier sesión abierta en otro dispositivo deja de poder rotar su refresh en el siguiente
    intento (401, mismo trato que un token inválido cualquiera). A diferencia de `revoke_family`
    (una sola familia, la del token presentado), esto no necesita conocer ningún token: basta con
    saber el `user_id`. `ttl_seconds` evita que la marca de generación quede para siempre en Redis:
    pasado ese tiempo ningún refresh emitido antes del cambio podría seguir vivo de todos modos
    (todos comparten el mismo TTL de vida que la propia cookie de refresh).
    """
    await redis.incr(_epoch_key(user_id))
    await redis.expire(_epoch_key(user_id), ttl_seconds)
