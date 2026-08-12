"""Cifrado en reposo por tenant (S5.2): pgcrypto (`pgp_sym_encrypt`/`pgp_sym_decrypt`) con una
clave derivada por tenant, nunca guardada en Postgres ni en ningún sitio — se recalcula en cada uso
a partir de `settings.db_encryption_master_key` (env var, igual que `JWT_SECRET`) y el `tenant_id`.

Dos claves DISTINTAS por tenant (spec S5.2 §4), derivadas con HKDF (RFC 5869) con un contexto
("info") distinto cada una, a partir de la MISMA clave maestra:
- **Clave de cifrado** (`derive_tenant_encryption_key`): pasada como contraseña a `pgp_sym_encrypt`/
  `pgp_sym_decrypt`. No determinista (pgcrypto añade IV aleatorio): dos cifrados del mismo valor dan
  bytes distintos, así que esta clave por sí sola no sirve para `WHERE`/`UNIQUE`.
- **Clave de índice ciego** (`blind_index`): un HMAC-SHA256 determinista del valor ya normalizado
  (para el CIF, vía `shared.tax_id.normalize_tax_id`), que SÍ permite igualdad exacta (`WHERE`,
  `UNIQUE`) sin poder invertirse al valor original. Solo se usa para el CIF (spec §0): los nombres
  no tienen índice ciego, no se pueden buscar por igualdad ni por texto libre, solo descifrar tras
  leer la fila completa.

Si se compromete la clave de índice (permite comparar, no leer), no sirve para descifrar los datos:
por eso son dos derivaciones distintas, nunca la misma clave para las dos cosas.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from shared.tax_id import normalize_tax_id

if TYPE_CHECKING:
    from shared.config import Settings

_ENCRYPTION_INFO_PREFIX = b"autoken:encryption-key:"
_INDEX_INFO_PREFIX = b"autoken:blind-index-key:"
_DERIVED_KEY_BYTES = 32


def _hkdf(master_key: str, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=_DERIVED_KEY_BYTES, salt=None, info=info).derive(
        master_key.encode("utf-8")
    )


def derive_tenant_encryption_key(master_key: str, tenant_id: str) -> str:
    """Clave de cifrado para este tenant, como texto hexadecimal (contraseña de `pgp_sym_encrypt`/
    `pgp_sym_decrypt`). Se recalcula en cada uso; nunca se persiste."""
    raw = _hkdf(master_key, _ENCRYPTION_INFO_PREFIX + tenant_id.encode("utf-8"))
    return raw.hex()


def derive_tenant_index_key(master_key: str, tenant_id: str) -> bytes:
    """Clave de índice ciego para este tenant (DISTINTA de la de cifrado, ver docstring del
    módulo)."""
    return _hkdf(master_key, _INDEX_INFO_PREFIX + tenant_id.encode("utf-8"))


def blind_index(master_key: str, tenant_id: str, normalized_value: str) -> str:
    """HMAC-SHA256 determinista de `normalized_value` con la clave de índice de este tenant.

    Determinista a propósito (mismo valor de entrada -> mismo índice siempre): es lo que permite
    `WHERE`/`UNIQUE` por igualdad exacta sin descifrar. No es reversible al valor original sin
    conocer la clave (a diferencia de un hash sin clave, vulnerable a diccionario/fuerza bruta).
    """
    key = derive_tenant_index_key(master_key, tenant_id)
    return hmac.new(key, normalized_value.encode("utf-8"), hashlib.sha256).hexdigest()


# --- Helpers de nivel de servicio (a partir de `Settings` ya resuelto) ---------------------------
# Único punto que cada contexto (companies, counterparty, invoicing, reporting, identity...) debe
# usar para derivar la clave/índice de un tenant a partir de la configuración de la app (spec S5.2
# §4, ADR-0018: "la clave de cifrado y la de índice ciego... nunca deriva el repositorio, ni cada
# servicio por su cuenta"). Antes de esta extracción (hallazgo de auditoría), cada contexto
# reimplementaba estas dos líneas por separado; un desajuste entre ellas (p. ej. olvidar normalizar
# antes del índice ciego en un sitio nuevo) rompería en silencio el filtro exacto de CIF (C5).


def tenant_encryption_key(settings: Settings, tenant_id: UUID | str) -> str:
    """Clave de cifrado de este tenant, derivada de `settings.db_encryption_master_key`."""
    return derive_tenant_encryption_key(settings.db_encryption_master_key, str(tenant_id))


def tenant_tax_id_blind_index(
    settings: Settings, tenant_id: UUID | str, raw_tax_id: str | None
) -> str | None:
    """Índice ciego de un CIF/NIF de este tenant, normalizando primero (`shared.tax_id.
    normalize_tax_id`) — el MISMO criterio de normalización en cada escritura y en cada filtro/
    lectura por igualdad, para que nunca diverjan. `None`/vacío -> `None` (nunca se indexa "la
    nada", spec §5: un CIF no legible sigue siendo NULL)."""
    if not raw_tax_id:
        return None
    canonical = normalize_tax_id(raw_tax_id)
    return blind_index(settings.db_encryption_master_key, str(tenant_id), canonical)


# Tabla -> columnas cifradas y si llevan índice ciego (spec S5.2). Fuente única para el código VIVO
# que necesita conocer este inventario (`platform_admin.repository` para el export del tenant,
# `jobs.key_rotation` para la rotación de clave). La migración 0020 mantiene su PROPIA copia
# congelada a propósito (una migración ya aplicada describe el esquema EN ESE MOMENTO, no debe
# acoplarse a una constante que puede cambiar después).
ENCRYPTED_COLUMNS: dict[str, dict[str, bool]] = {
    "companies": {"cif": True, "name": False},
    "counterparties": {"cif": True, "name": False},
    "invoices": {"counterparty_tax_id": True, "counterparty_name": False},
    "ocr_extractions": {"counterparty_tax_id": False, "counterparty_name": False},
    "ocr_comparison_runs": {
        "original_counterparty_tax_id": False,
        "original_counterparty_name": False,
        "enhanced_counterparty_tax_id": False,
        "enhanced_counterparty_name": False,
    },
    "ocr_ranking_entries": {"counterparty_tax_id": False, "counterparty_name": False},
    "ocr_benchmark_results": {"counterparty_tax_id": False, "counterparty_name": False},
}
