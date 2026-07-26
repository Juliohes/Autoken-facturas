"""Test de comportamiento de la migración 0020 (S5.2 C8): backfill de datos ya existentes.

A diferencia del resto de la suite (que arranca `provision_test_db()` con TODAS las migraciones ya
aplicadas, incluida 0020, sin datos previos que migrar), este test crea su PROPIA base de datos
efímera, la deja justo ANTES de 0020 (con datos sembrados en texto plano, el estado real de
producción antes de esta tarea), y comprueba que `alembic upgrade head` los deja cifrados y
legibles por la aplicación — el escenario C8 de la spec, que ningún otro test ejercita.
"""

from __future__ import annotations

import asyncio
import os
import sys
from uuid import uuid4

import asyncpg

from shared.config import get_settings
from shared.encryption import blind_index, derive_tenant_encryption_key

_ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432"
)
_DB_NAME = "autoken_test_migration_0020"
_PRE_REVISION = "0019_ocr_ranking_entries"


async def _run_alembic(db_dsn: str, revision: str) -> None:
    async_url = db_dsn.replace("postgresql://", "postgresql+asyncpg://")
    env = {**os.environ, "DATABASE_URL": async_url}
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        revision,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"alembic upgrade {revision} falló:\n{out.decode()}")


async def test_c8_migracion_cifra_los_datos_ya_existentes() -> None:
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
    try:
        await _run_alembic(db_dsn, _PRE_REVISION)

        tenant_id = str(uuid4())
        company_id = str(uuid4())
        counterparty_cif = "B06183446"
        counterparty_name = "Proveedor Preexistente SA"
        conn = await asyncpg.connect(db_dsn)
        try:
            await conn.execute(
                "INSERT INTO tenants (id, slug, name, status) VALUES ($1, $2, $3, 'active')",
                tenant_id,
                f"pre-s52-{tenant_id[:8]}",
                "Asesoria Pre-S5.2",
            )
            await conn.execute(
                "INSERT INTO companies (id, tenant_id, name, cif, status) "
                "VALUES ($1, $2, 'Mi Empresa Preexistente SL', 'A39031620', 'active')",
                company_id,
                tenant_id,
            )
            await conn.execute(
                "INSERT INTO counterparties "
                "(tenant_id, cif, name, name_source, times_seen, verified_at) "
                "VALUES ($1, $2, $3, 'human', 1, now())",
                tenant_id,
                counterparty_cif,
                counterparty_name,
            )
        finally:
            await conn.close()

        # Migración de S5.2: aquí ocurre el backfill (texto plano -> cifrado + índice ciego).
        await _run_alembic(db_dsn, "head")

        conn = await asyncpg.connect(db_dsn)
        try:
            company_row = await conn.fetchrow(
                "SELECT cif, name, cif_blind_index FROM companies WHERE id = $1", company_id
            )
            counterparty_row = await conn.fetchrow(
                "SELECT cif, name, cif_blind_index FROM counterparties WHERE tenant_id = $1",
                tenant_id,
            )
        finally:
            await conn.close()

        master_key = get_settings().db_encryption_master_key
        tenant_key = derive_tenant_encryption_key(master_key, tenant_id)

        # C1: la columna cruda ya no es el texto plano original (ni parcialmente reconocible).
        assert isinstance(company_row["cif"], bytes)
        assert b"A39031620" not in company_row["cif"]
        assert isinstance(counterparty_row["name"], bytes)
        assert counterparty_name.encode() not in counterparty_row["name"]

        # C2/C8: la aplicación (vía pgp_sym_decrypt con la clave del tenant) recupera el original.
        conn = await asyncpg.connect(db_dsn)
        try:
            decrypted_company_cif = await conn.fetchval(
                "SELECT pgp_sym_decrypt($1::bytea, $2)::text", company_row["cif"], tenant_key
            )
            decrypted_company_name = await conn.fetchval(
                "SELECT pgp_sym_decrypt($1::bytea, $2)::text", company_row["name"], tenant_key
            )
            decrypted_counterparty_cif = await conn.fetchval(
                "SELECT pgp_sym_decrypt($1::bytea, $2)::text", counterparty_row["cif"], tenant_key
            )
        finally:
            await conn.close()

        assert decrypted_company_cif == "A39031620"
        assert decrypted_company_name == "Mi Empresa Preexistente SL"
        assert decrypted_counterparty_cif == counterparty_cif

        # C3/C8: el índice ciego del backfill coincide con el que calcularía la aplicación hoy.
        assert company_row["cif_blind_index"] == blind_index(master_key, tenant_id, "A39031620")
        assert counterparty_row["cif_blind_index"] == blind_index(
            master_key, tenant_id, counterparty_cif
        )
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
