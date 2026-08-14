"""Migración S6.12 de deduplicación privada sobre documentos ya existentes."""

from __future__ import annotations

import asyncio
import os
import sys
from uuid import uuid4

import asyncpg
import pytest

from shared.config import get_settings
from shared.encryption import derive_tenant_encryption_key

_ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432"
)
_DB_NAME = "autoken_test_migration_0038"
_PRE_REVISION = "0037_multipage_uploaded_files"


async def _run_alembic(db_dsn: str, revision: str) -> None:
    async_url = db_dsn.replace("postgresql://", "postgresql+asyncpg://")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        revision,
        env={**os.environ, "DATABASE_URL": async_url},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"alembic upgrade {revision} falló:\n{out.decode()}")


async def test_migracion_hereda_el_autor_de_paginas_y_hace_privado_el_hash() -> None:
    root = await asyncpg.connect(f"{_ADMIN_DSN}/postgres")
    try:
        await root.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{_DB_NAME}' AND pid <> pg_backend_pid()"
        )
        await root.execute(f'DROP DATABASE IF EXISTS "{_DB_NAME}"')
        await root.execute(f'CREATE DATABASE "{_DB_NAME}"')
    finally:
        await root.close()

    db_dsn = f"{_ADMIN_DSN}/{_DB_NAME}"
    tenant_id, company_id, first_user, second_user, first_file = (str(uuid4()) for _ in range(5))
    page_hash = "p" * 64
    try:
        await _run_alembic(db_dsn, _PRE_REVISION)
        conn = await asyncpg.connect(db_dsn)
        try:
            key = derive_tenant_encryption_key(get_settings().db_encryption_master_key, tenant_id)
            await conn.execute(
                "INSERT INTO tenants (id, slug, name, status) "
                "VALUES ($1, $2, 'Pre S6.12', 'active')",
                tenant_id,
                f"pre-s612-{tenant_id[:8]}",
            )
            await conn.execute(
                "INSERT INTO companies (id, tenant_id, name, cif, cif_blind_index, status) "
                "VALUES ($1, $2, pgp_sym_encrypt('Empresa', $3), pgp_sym_encrypt('A39031620', $3), "
                "'blind-index', 'active')",
                company_id,
                tenant_id,
                key,
            )
            for user_id, email in (
                (first_user, "first@example.test"),
                (second_user, "second@example.test"),
            ):
                await conn.execute(
                    "INSERT INTO users (id, tenant_id, email, role, status) "
                    "VALUES ($1, $2, $3, 'user', 'active')",
                    user_id,
                    tenant_id,
                    email,
                )
            await conn.execute(
                "INSERT INTO uploaded_files "
                "(id, tenant_id, company_id, uploaded_by, storage_bucket, storage_key, "
                "content_type, "
                "size_bytes, sha256) VALUES ($1,$2,$3,$4,'test','root','image/jpeg',1,$5)",
                first_file,
                tenant_id,
                company_id,
                first_user,
                "r" * 64,
            )
            await conn.execute(
                "INSERT INTO uploaded_file_pages "
                "(root_uploaded_file_id, company_id, page_number, storage_bucket, storage_key, "
                "content_type, size_bytes, sha256) "
                "VALUES ($1,$2,2,'test','page','image/jpeg',1,$3)",
                first_file,
                company_id,
                page_hash,
            )
        finally:
            await conn.close()

        await _run_alembic(db_dsn, "head")
        conn = await asyncpg.connect(db_dsn)
        try:
            assert (
                str(
                    await conn.fetchval(
                        "SELECT uploaded_by FROM uploaded_file_pages "
                        "WHERE root_uploaded_file_id = $1",
                        first_file,
                    )
                )
                == first_user
            )
            second_file = str(uuid4())
            await conn.execute(
                "INSERT INTO uploaded_files "
                "(id, tenant_id, company_id, uploaded_by, storage_bucket, storage_key, "
                "content_type, "
                "size_bytes, sha256) VALUES ($1,$2,$3,$4,'test','root-2','image/jpeg',1,$5)",
                second_file,
                tenant_id,
                company_id,
                second_user,
                "r" * 64,
            )
            await conn.execute(
                "INSERT INTO uploaded_file_pages "
                "(root_uploaded_file_id, company_id, uploaded_by, page_number, storage_bucket, "
                "storage_key, content_type, size_bytes, sha256) "
                "VALUES ($1,$2,$3,2,'test','page-2','image/jpeg',1,$4)",
                second_file,
                company_id,
                second_user,
                page_hash,
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO uploaded_files "
                    "(tenant_id, company_id, uploaded_by, storage_bucket, storage_key, "
                    "content_type, "
                    "size_bytes, sha256) VALUES ($1,$2,$3,'test','duplicate','image/jpeg',1,$4)",
                    tenant_id,
                    company_id,
                    first_user,
                    page_hash,
                )
        finally:
            await conn.close()
    finally:
        root = await asyncpg.connect(f"{_ADMIN_DSN}/postgres")
        try:
            await root.execute(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{_DB_NAME}' AND pid <> pg_backend_pid()"
            )
            await root.execute(f'DROP DATABASE IF EXISTS "{_DB_NAME}"')
        finally:
            await root.close()
