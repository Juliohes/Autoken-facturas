"""Cifrado de los backups completos de base de datos (S5.3).

AES-256-GCM con una clave DISTINTA de la de cifrado de columnas (S5.2, `shared/encryption.py`) a
propósito: protegen modelos de amenaza distintos (un backup robado vs. una fila de una tabla), y
rotar uno no debe forzar rotar el otro (spec S5.3 §2, ADR-0019).

Formato del fichero cifrado: `nonce (12 bytes) || ciphertext+tag (AES-GCM)`. GCM autentica el
contenido: una clave incorrecta o un fichero truncado/corrupto fallan al descifrar con un error
claro (`InvalidTag`), nunca devuelven datos parciales o reinterpretados en silencio (spec C2/C5).
"""

from __future__ import annotations

import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12
_KEY_BYTES = 32


class BackupDecryptionError(Exception):
    """La clave no coincide o el fichero está truncado/corrupto."""


def _derive_key(passphrase: str) -> bytes:
    """Normaliza `passphrase` (de cualquier longitud) a una clave AES-256 de 32 bytes.

    Igual que `jwt_secret`/`db_encryption_master_key`, `backup_encryption_key` es un secreto de
    texto libre (no se exige que el operador genere exactamente 32 bytes en base64) — se deriva con
    SHA-256, no se usa tal cual como clave AES.
    """
    return hashlib.sha256(passphrase.encode("utf-8")).digest()


def encrypt_backup(passphrase: str, data: bytes) -> bytes:
    """Cifra `data` (el volcado de `pg_dump`) con AES-256-GCM. Nunca determinista (nonce aleatorio):
    dos cifrados del mismo backup dan bytes distintos."""
    key = _derive_key(passphrase)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, data, associated_data=None)
    return nonce + ciphertext


def decrypt_backup(passphrase: str, blob: bytes) -> bytes:
    """Descifra un backup cifrado con `encrypt_backup`. Clave incorrecta o `blob` truncado/corrupto
    -> `BackupDecryptionError` (nunca datos parciales)."""
    if len(blob) < _NONCE_BYTES:
        raise BackupDecryptionError("El fichero de backup es demasiado corto para ser válido.")
    key = _derive_key(passphrase)
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
    except InvalidTag as exc:
        raise BackupDecryptionError(
            "No se pudo descifrar el backup: clave incorrecta o fichero corrupto/truncado."
        ) from exc
