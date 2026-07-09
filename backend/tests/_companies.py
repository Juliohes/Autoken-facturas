"""Utilidades de test para el contexto `companies` (S1.5).

No es un módulo de tests (prefijo `_`): constantes de CIF/NIF (reales del Excel de Setex, para no
chocar con el validador de dígito de control), siembra de un `tenant_admin`, obtención de su token y
un constructor de ficheros `.xlsx` en memoria para los tests de importación.
"""

from __future__ import annotations

import io

import httpx

from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, login
from tests._dbtest import seed_tenant, seed_user

COMPANIES = "/api/v1/companies"
IMPORT = "/api/v1/companies/import"
REAL_XLSX = "/opt/app-facturas/entregas/Empresas_CIF_NIF.xlsx"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Identificadores fiscales VÁLIDOS (dígito de control correcto), tomados del Excel real.
VALID_CIF = "A39031620"  # 3L INTERNACIONAL (sociedad)
VALID_CIF_2 = "B06183446"  # AGRICOLA CIPRIANO, S.L.
VALID_NIF = "76072394D"  # ALBERTO CAÑA REGALADO (autónomo)
# INVÁLIDO: mismo número de NIF con la letra de control equivocada (la correcta es D).
INVALID_TAXID = "76072394X"


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
