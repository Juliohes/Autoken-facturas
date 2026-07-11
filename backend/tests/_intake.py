"""Utilidades de test para el contexto `invoice_intake` (S2.1 Upload seguro).

No es un módulo de tests (prefijo `_`): reúne el contrato HTTP del endpoint de subida, bytes de
ficheros de prueba (JPEG/PNG/PDF válidos por número mágico, un no-imagen, y un JPEG con la firma
EICAR embebida para el antivirus), siembra de un empleado con su empresa y de un admin, y helpers
para consultar el efecto (fila en `uploaded_files`, entrada en `audit_log`, objeto en MinIO).

Contrato que el `implementer` debe respetar (lo fija esta fase roja):
- `POST /api/v1/uploads` multipart: parte `file` (el fichero) + campo `company_id` (uuid str).
- Éxito -> 201 con JSON: id, company_id, content_type (MIME REAL), size_bytes, sha256,
  status="pending_ocr", scan_status="clean", created_at.
- Duplicado en la misma empresa -> 409 con `duplicate_of` = id del original.
- Tipo no admitido -> 415; demasiado grande -> 413; infectado o vacío -> 422; sin auth -> 401;
  empresa ajena del propio tenant -> 403; empresa de otro tenant -> 404; dependencia (AV/almacén)
  caída -> 503.
- Almacenamiento: bucket `tenant-{tenant_id}`, objeto con clave `{company_id}/{sha256}`.
- El router llama a funciones de módulo (para poder inyectar fallos en test):
  `invoice_intake.scanner.scan(content)` (lanza `scanner.ScannerUnavailable` si el AV no responde)
  y `invoice_intake.storage.put_object(bucket, key, data, length, content_type)`.
"""

from __future__ import annotations

import asyncpg
import httpx

from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, bearer, host, login
from tests._dbtest import seed_company, seed_membership, seed_tenant, seed_user

UPLOADS = "/api/v1/uploads"

# --- Bytes de ficheros de prueba (válidos por número mágico, mínimos) ----------------------------
# JPEG: cabecera JFIF (FF D8 FF E0 ... ) + relleno + marcador de fin (FF D9). Sniff -> image/jpeg.
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000") + b"\x00" * 64 + b"\xff\xd9"
# PNG: firma de 8 bytes + IHDR mínimo. Sniff -> image/png.
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + b"\x00" * 32
# PDF: cabecera %PDF + fin. Sniff -> application/pdf.
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
# No es imagen ni PDF (cabecera de ejecutable PE). Debe rechazarse por MIME real (415).
NOT_AN_IMAGE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 48

# Cadena EICAR estándar de prueba de antivirus (inofensiva; todos los AV la detectan).
EICAR = (r"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*").encode("ascii")
# JPEG válido (empieza por FF D8 FF -> pasa el MIME real) con la firma EICAR embebida antes del fin:
# comprueba que un fichero del tipo correcto pero infectado se rechaza (C6).
EICAR_JPEG = JPEG[:-2] + EICAR + b"\xff\xd9"

JPEG_CT = "image/jpeg"
PNG_CT = "image/png"
PDF_CT = "application/pdf"


def auth(token: str, hostname: str = "ilex.localhost") -> dict[str, str]:
    return {**host(hostname), **bearer(token)}


def upload_parts(content: bytes, company_id: str, *, filename: str, content_type: str) -> dict:
    """Argumentos multipart para `client.post(UPLOADS, **upload_parts(...))`."""
    return {
        "files": {"file": (filename, content, content_type)},
        "data": {"company_id": company_id},
    }


async def seed_uploader(
    dsns: dict[str, str],
    *,
    slug: str = "ilex",
    name: str = "I-Lex Asesoría",
    email: str = "ana@ilex.es",
    company_cif: str = "A39031620",
) -> tuple[str, str, str]:
    """Siembra tenant + empleado (`user`) con contraseña + su empresa + membership.

    Devuelve (tenant_id, user_id, company_id). El empleado sube facturas de SU empresa.
    """
    tenant_id = await seed_tenant(dsns["admin"], slug, name)
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email=email,
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name=f"{name} Empresa", cif=company_cif
    )
    await seed_membership(
        dsns["admin"], user_id=user_id, company_id=company_id, tenant_id=tenant_id
    )
    return tenant_id, user_id, company_id


async def seed_tenant_admin(
    dsns: dict[str, str],
    *,
    slug: str = "ilex",
    name: str = "I-Lex Asesoría",
    email: str = "admin@ilex.es",
) -> tuple[str, str]:
    """Siembra tenant + `tenant_admin` con contraseña. Devuelve (tenant_id, admin_id)."""
    tenant_id = await seed_tenant(dsns["admin"], slug, name)
    admin_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email=email,
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    return tenant_id, admin_id


async def token_for(
    client: httpx.AsyncClient, *, email: str, hostname: str = "ilex.localhost"
) -> str:
    """Access token de una identidad con contraseña (empleado o admin), sin TOTP."""
    resp = await login(client, hostname, email, USER_PASSWORD)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# --- Consultas de efecto (superusuario, saltando RLS) --------------------------------------------
async def count_uploaded_files(
    dsns: dict[str, str], *, company_id: str, sha256: str | None = None
) -> int:
    """Número de filas en `uploaded_files` de una empresa (opcionalmente con un sha256 dado)."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        if sha256 is None:
            row = await conn.fetchval(
                "SELECT count(*) FROM uploaded_files WHERE company_id = $1", company_id
            )
        else:
            row = await conn.fetchval(
                "SELECT count(*) FROM uploaded_files WHERE company_id = $1 AND sha256 = $2",
                company_id,
                sha256,
            )
        return int(row)
    finally:
        await conn.close()


async def audit_entries(dsns: dict[str, str], *, action: str, entity_id: str) -> int:
    """Número de entradas en `audit_log` con una acción y entidad dadas."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchval(
            "SELECT count(*) FROM audit_log WHERE action = $1 AND entity_id = $2",
            action,
            entity_id,
        )
        return int(row)
    finally:
        await conn.close()


async def object_exists(*, tenant_id: str, company_id: str, sha256: str) -> bool:
    """¿Existe el objeto en MinIO? (import perezoso del almacén de producción, solo en verde).

    Usa las funciones dueñas del formato bucket/clave (`storage.bucket_for`/`key_for`), única fuente
    de la convención de layout: el helper no la duplica.
    """
    from invoice_intake import storage

    bucket = storage.bucket_for(tenant_id)
    key = storage.key_for(company_id, sha256)
    return storage.object_exists(bucket, key)
