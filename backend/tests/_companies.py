"""Utilidades de test para el contexto `companies` (S1.5).

No es un módulo de tests (prefijo `_`): constantes de CIF/NIF, un generador de NIFs válidos
(dígito de control correcto) para los tests de importación masiva, siembra de un `tenant_admin`,
obtención de su token y un constructor de ficheros `.xlsx` en memoria. NO depende de datos reales de
clientes: el Excel de Setex vive en `entregas/` (gitignored) y no está disponible en CI.
"""

from __future__ import annotations

import io

import httpx

from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, login
from tests._dbtest import seed_tenant, seed_user

COMPANIES = "/api/v1/companies"
IMPORT = "/api/v1/companies/import"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Identificadores fiscales VÁLIDOS de prueba (dígito de control correcto; forma real de CIF y NIF).
VALID_CIF = "A39031620"  # CIF de sociedad
VALID_CIF_2 = "B06183446"  # CIF de sociedad
VALID_NIF = "76072394D"  # NIF de autónomo
# INVÁLIDO: mismo número de NIF con la letra de control equivocada (la correcta es D).
INVALID_TAXID = "76072394X"

_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def valid_nif(number: int) -> str:
    """NIF válido (letra de control correcta) para un número dado; genera identificadores únicos.

    Usa el mismo algoritmo módulo-23 que `validate_tax_id`, así que el resultado siempre pasa la
    validación. Permite construir importaciones de N empresas sin el Excel real (gitignored).
    """
    body = number % 100_000_000
    return f"{body:08d}{_NIF_LETTERS[body % 23]}"


async def seed_admin(
    dsns: dict[str, str], *, slug: str = "ilex", email: str = "admin@ilex.es"
) -> tuple[str, str]:
    """Siembra un tenant y un `tenant_admin` con contraseña. Devuelve (tenant_id, admin_id)."""
    tenant_id = await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")
    admin_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email=email,
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    return tenant_id, admin_id


async def admin_token(
    client: httpx.AsyncClient, *, email: str = "admin@ilex.es", hostname: str = "ilex.localhost"
) -> str:
    """Access token de un `tenant_admin` (sin TOTP)."""
    resp = await login(client, hostname, email, USER_PASSWORD)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def build_xlsx(
    rows: list[tuple[str, ...]], *, header: tuple[str, ...] = ("Nombre", "CIF/NIF")
) -> bytes:
    """Construye un `.xlsx` en memoria con cabecera y filas (para los tests de importación)."""
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(list(header))
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
