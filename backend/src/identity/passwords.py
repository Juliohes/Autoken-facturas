"""Hashing y verificación de contraseñas con Argon2id (S1.3, ADR-0012).

Solo se persiste el hash Argon2id (`users.password_hash`); la contraseña en claro nunca se guarda
ni se registra. Para no filtrar por latencia si un email no existe (anti-enumeración, §4 de la
spec), la verificación se ejecuta también cuando no hay usuario: `verify_password` hashea contra un
hash señuelo cuando recibe `None`, de modo que el coste temporal es comparable al de un fallo real.
"""

from __future__ import annotations

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from shared.config import Settings

_hasher = PasswordHasher()

# Hash señuelo para equalizar el tiempo cuando el usuario no existe o no tiene contraseña. Se
# calcula una vez al importar; su contraseña real es irrelevante (nunca se compara con éxito).
_DUMMY_HASH = _hasher.hash("timing-equalization-decoy-password")


def validate_password_policy(password: str, settings: Settings) -> bool:
    """Política única de contraseña: `min_length <= len(password) <= max_length`.

    Fuente única de los límites (§4 de la spec, ADR-0012): la usan la activación (que rechaza con
    422 lo que no cumpla) y el corte de longitud del login (que evita gastar el coste de hashing en
    contraseñas fuera de rango, defensa DoS). No se reimplementan los límites en dos sitios.
    """
    return settings.password_min_length <= len(password) <= settings.password_max_length


def hash_password(password: str) -> str:
    """Devuelve el hash Argon2id de `password` (lo único que se persiste)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verifica la contraseña contra su hash. Con `password_hash=None` gasta tiempo y da False.

    El hashing se ejecuta siempre (incluso sin usuario) para no revelar por latencia si la cuenta
    existe. Devuelve True solo cuando había un hash real y la contraseña coincide.
    """
    target = password_hash if password_hash is not None else _DUMMY_HASH
    try:
        _hasher.verify(target, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def verify_legacy_bcrypt(password: str, legacy_bcrypt_hash: str) -> bool:
    """Verifica `password` contra un hash bcrypt heredado (migración perezosa, migración 0022).

    Solo se llama cuando `password_hash` (Argon2id) todavía es `None` — cuentas reales importadas
    de Setex que aún no han hecho su primer login en la app nueva. Un hash inválido/corrupto se
    trata como "no coincide", nunca como error 500 (mismo criterio defensivo que `verify_password`).
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), legacy_bcrypt_hash.encode("utf-8"))
    except ValueError:
        return False
