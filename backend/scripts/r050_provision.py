"""Provisiona y limpia el tenant efímero usado por la carga sintética R-050.

El script usa un DSN de administrador solo para preparar datos de prueba. Nunca crea una cuenta en
Setex ni escribe credenciales en el repositorio; el JSON de salida debe permanecer fuera de Git.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import asyncpg

from identity.passwords import hash_password
from invoice_intake import storage
from shared.encryption import blind_index, derive_tenant_encryption_key
from shared.config import get_settings


def _admin_dsn() -> str:
    value = os.environ.get("R050_ADMIN_DSN")
    if not value:
        raise RuntimeError("Falta R050_ADMIN_DSN; no se acepta un DSN de producción implícito")
    return value


async def provision(output: Path) -> None:
    settings = get_settings()
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    slug = f"r050-{uuid4().hex[:10]}"
    password = f"R050-load-{uuid4().hex[:16]}"
    cif = "B06400980"
    key = derive_tenant_encryption_key(settings.db_encryption_master_key, tenant_id)
    cif_index = blind_index(settings.db_encryption_master_key, tenant_id, cif)
    users: list[dict[str, str]] = []

    conn = await asyncpg.connect(_admin_dsn())
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO tenants (id, slug, name, status, is_demo) VALUES ($1, $2, $3, 'active', true)",
                tenant_id,
                slug,
                f"Carga sintética {slug}",
            )
            await conn.execute(
                "INSERT INTO companies (id, tenant_id, name, cif, cif_blind_index, status) "
                "VALUES ($1, $2, pgp_sym_encrypt($3, $4), pgp_sym_encrypt($5, $4), $6, 'active')",
                company_id,
                tenant_id,
                "Empresa sintética R050",
                key,
                cif,
                cif_index,
            )
            for index in range(1, 11):
                user_id = str(uuid4())
                email = f"{slug}-{index:02d}@example.test"
                await conn.execute(
                    "INSERT INTO users (id, tenant_id, email, role, status, password_hash) "
                    "VALUES ($1, $2, $3, 'user', 'active', $4)",
                    user_id,
                    tenant_id,
                    email,
                    hash_password(password),
                )
                await conn.execute(
                    "INSERT INTO memberships (user_id, company_id, tenant_id) VALUES ($1, $2, $3)",
                    user_id,
                    company_id,
                    tenant_id,
                )
                users.append({"email": email, "password": password, "company_id": company_id})
    finally:
        await conn.close()

    output.write_text(
        json.dumps(
            {
                "base_url": os.environ.get("R050_BASE_URL", "http://127.0.0.1:18050"),
                "tenant_host": f"{slug}.autoken.es",
                "tenant_id": tenant_id,
                "company_id": company_id,
                "users": users,
                "uploads_per_user": 10,
                "poll_timeout_seconds": 180,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"tenant_id": tenant_id, "tenant_host": f"{slug}.autoken.es"}))


async def cleanup(tenant_id: str) -> None:
    bucket = storage.bucket_for(tenant_id)
    await asyncio.to_thread(storage.remove_bucket_recursive, bucket)
    conn = await asyncpg.connect(_admin_dsn())
    try:
        async with conn.transaction():
            await conn.execute("DELETE FROM uploaded_files WHERE tenant_id = $1", tenant_id)
            await conn.execute("DELETE FROM users WHERE tenant_id = $1", tenant_id)
            await conn.execute("DELETE FROM tenants WHERE id = $1", tenant_id)
    finally:
        await conn.close()
    print(json.dumps({"cleaned_tenant_id": tenant_id, "bucket": bucket}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, help="JSON local de configuración de carga")
    parser.add_argument("--cleanup-tenant", help="Tenant efímero que se debe eliminar")
    args = parser.parse_args()
    if bool(args.out) == bool(args.cleanup_tenant):
        parser.error("indica exactamente uno de --out o --cleanup-tenant")
    if args.out:
        asyncio.run(provision(args.out))
    else:
        asyncio.run(cleanup(args.cleanup_tenant))


if __name__ == "__main__":
    main()
