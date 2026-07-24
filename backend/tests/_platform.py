"""Utilidades de test del panel de plataforma (S4.1): sembrar y autenticar un `platform_admin`.

No es un módulo de tests (prefijo `_`): reutiliza tal cual los helpers de S1.3 (`seed_user` con
`tenant_id=None`, login con contraseña + TOTP en `panel.localhost`) para no repetir ese flujo en
cada test de `platform_admin`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import asyncpg
import httpx

from tests._auth import PLATFORM_PASSWORD, PLATFORM_PASSWORD_HASH, TOTP_SECRET, login, totp_now
from tests._dbtest import seed_user

PANEL_HOST = "panel.localhost"


async def seed_platform_admin(dsns: dict[str, str], *, email: str = "julio@autoken.es") -> str:
    """Siembra un `platform_admin` (sin tenant) con contraseña y TOTP ya listos. Devuelve su id."""
    return await seed_user(
        dsns["admin"],
        tenant_id=None,
        email=email,
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )


async def platform_token(client: httpx.AsyncClient, *, email: str = "julio@autoken.es") -> str:
    """Access token de un `platform_admin` ya sembrado (login real por `panel.localhost`)."""
    resp = await login(client, PANEL_HOST, email, PLATFORM_PASSWORD, totp_code=totp_now())
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def fetch_tenant_by_slug(dsns: dict[str, str], *, slug: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow("SELECT * FROM tenants WHERE slug = $1", slug)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def fetch_branding(dsns: dict[str, str], *, tenant_id: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow("SELECT * FROM tenant_branding WHERE tenant_id = $1", tenant_id)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def count_tenants(dsns: dict[str, str]) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(await conn.fetchval("SELECT count(*) FROM tenants"))
    finally:
        await conn.close()


async def fetch_tenant_by_id(dsns: dict[str, str], *, tenant_id: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow("SELECT * FROM tenants WHERE id = $1", tenant_id)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def count_companies(dsns: dict[str, str], *, tenant_id: str) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(
            await conn.fetchval("SELECT count(*) FROM companies WHERE tenant_id = $1", tenant_id)
        )
    finally:
        await conn.close()


def bucket_exists(tenant_id: str) -> bool:
    """¿Existe el bucket de MinIO del tenant? (S4.4, import perezoso del almacén de producción)."""
    from invoice_intake import storage

    return storage._client().bucket_exists(storage.bucket_for(tenant_id))


async def seed_ocr_extraction(
    dsns: dict[str, str],
    *,
    tenant_id: str,
    company_id: str,
    seed: int = 0,
    uploaded_by: str | None = None,
    status: str = "ok",
) -> str:
    """Inserta una extracción OCR mínima (S4.5): `uploaded_file` + fila de `ocr_extractions`.
    Contenido irrelevante, solo cuenta para las métricas de consumo.

    `seed` varía el contenido subido para no chocar con el UNIQUE `(company_id, sha256)` de
    `uploaded_files` al sembrar varias extracciones de la misma empresa. `uploaded_by`: reutiliza un
    usuario existente (por defecto crea uno nuevo `active`, que ya cuenta como consumo por sí solo —
    pasar uno explícito cuando el test controla el número exacto de usuarios activos, S4.5 C1).
    `status`: `ocr_extractions_count` cuenta cualquiera (spec S4.5 §0 decisión 5), por defecto `ok`.
    """
    from tests._ocr import JPEG, seed_uploaded_file

    uploader = uploaded_by or await seed_user(
        dsns["admin"], tenant_id=tenant_id, email=f"seed-ocr-{uuid4()}@example.com"
    )
    file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=uploader,
        content=JPEG + bytes([seed % 256]),
    )
    extraction_id = str(uuid4())
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "INSERT INTO ocr_extractions (id, tenant_id, company_id, uploaded_file_id, "
            "tax_lines, own_tax_id_present, confidences, validations, engine, model, raw, status) "
            "VALUES ($1,$2,$3,$4,'[]'::jsonb,false,'{}'::jsonb,'{}'::jsonb,'test','test',"
            "'{}'::jsonb,$5)",
            extraction_id,
            tenant_id,
            company_id,
            file_id,
            status,
        )
    finally:
        await conn.close()
    return extraction_id


async def seed_audit_log(
    dsns: dict[str, str], *, tenant_id: str, at: datetime, action: str = "test.action"
) -> None:
    """Inserta una entrada de `audit_log` con un `at` concreto (S4.5, "último uso")."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "INSERT INTO audit_log (id, tenant_id, action, entity, at) VALUES ($1,$2,$3,'test',$4)",
            str(uuid4()),
            tenant_id,
            action,
            at,
        )
    finally:
        await conn.close()
