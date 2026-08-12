"""Test de comportamiento S6.7 C24: la migración 0033 cifra el histórico experimental.

Se crea una base efímera justo antes de la migración, cuando CIF/nombre todavía vivían dentro de los
JSONB de `ocr_comparison_runs` y `ocr_ranking_entries`, igual que el estado real de producción.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from uuid import uuid4

import asyncpg

from shared.config import get_settings
from shared.encryption import derive_tenant_encryption_key

_ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432"
)
_DB_NAME = "autoken_test_migration_0033"
_PRE_REVISION = "0032_benchmark_field_ranking"


async def _run_alembic(db_dsn: str, direction: str, revision: str) -> None:
    async_url = db_dsn.replace("postgresql://", "postgresql+asyncpg://")
    env = {**os.environ, "DATABASE_URL": async_url}
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        direction,
        revision,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"alembic {direction} {revision} falló:\n{out.decode()}")


async def test_c24_migracion_cifra_las_lecturas_experimentales_ya_existentes() -> None:
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
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    user_id = str(uuid4())
    file_id = str(uuid4())
    tax_id = "B06183446"
    name = "Proveedor Experimental Preexistente SA"
    try:
        await _run_alembic(db_dsn, "upgrade", _PRE_REVISION)
        conn = await asyncpg.connect(db_dsn)
        try:
            key = derive_tenant_encryption_key(get_settings().db_encryption_master_key, tenant_id)
            await conn.execute(
                "INSERT INTO tenants (id, slug, name, status) VALUES ($1, $2, $3, 'active')",
                tenant_id,
                f"pre-s67-{tenant_id[:8]}",
                "Asesoria Pre-S6.7",
            )
            await conn.execute(
                "INSERT INTO companies (id, tenant_id, name, cif, cif_blind_index, status) "
                "VALUES ($1, $2, pgp_sym_encrypt($3, $5), pgp_sym_encrypt($4, $5), $6, 'active')",
                company_id,
                tenant_id,
                "Empresa de prueba",
                "A39031620",
                key,
                "indice-de-prueba",
            )
            await conn.execute(
                "INSERT INTO users (id, tenant_id, email, role, status) "
                "VALUES ($1, $2, $3, 'user', 'active')",
                user_id,
                tenant_id,
                f"pre-s67-{tenant_id[:8]}@example.test",
            )
            await conn.execute(
                "INSERT INTO uploaded_files "
                "(id, tenant_id, company_id, uploaded_by, content_type, size_bytes, "
                "sha256, storage_bucket, storage_key, status) "
                "VALUES ($1, $2, $3, $4, 'image/jpeg', 1, $5, 'test', $6, "
                "'confirmed')",
                file_id,
                tenant_id,
                company_id,
                user_id,
                "a" * 64,
                f"tenant-{tenant_id}/{file_id}",
            )
            reading = {
                "counterparty_tax_id": tax_id,
                "counterparty_name": name,
                "total_amount": "121",
            }
            await conn.execute(
                "INSERT INTO ocr_comparison_runs "
                "(tenant_id, company_id, uploaded_file_id, original_reading, enhanced_reading, "
                "original_score, enhanced_score, winner, engine, model) "
                "VALUES ($1, $2, $3, $4::jsonb, $4::jsonb, 4, 4, 'tie', 'fake', 'fake-v1')",
                tenant_id,
                company_id,
                file_id,
                json.dumps(reading),
            )
            await conn.execute(
                "INSERT INTO ocr_ranking_entries "
                "(tenant_id, company_id, uploaded_file_id, engine, model, reading, score) "
                "VALUES ($1, $2, $3, 'fake', 'fake-v1', $4::jsonb, 4)",
                tenant_id,
                company_id,
                file_id,
                json.dumps(reading),
            )
        finally:
            await conn.close()

        await _run_alembic(db_dsn, "upgrade", "head")

        conn = await asyncpg.connect(db_dsn)
        try:
            comparison = await conn.fetchrow(
                "SELECT original_reading, enhanced_reading, original_counterparty_tax_id, "
                "original_counterparty_name, enhanced_counterparty_tax_id, "
                "enhanced_counterparty_name "
                "FROM ocr_comparison_runs WHERE uploaded_file_id = $1",
                file_id,
            )
            ranking = await conn.fetchrow(
                "SELECT reading, counterparty_tax_id, counterparty_name "
                "FROM ocr_ranking_entries WHERE uploaded_file_id = $1",
                file_id,
            )
            decrypted = await conn.fetchrow(
                "SELECT pgp_sym_decrypt(original_counterparty_tax_id, $2)::text AS "
                "comparison_tax_id, "
                "pgp_sym_decrypt(original_counterparty_name, $2)::text AS comparison_name, "
                "pgp_sym_decrypt(counterparty_tax_id, $2)::text AS ranking_tax_id, "
                "pgp_sym_decrypt(counterparty_name, $2)::text AS ranking_name "
                "FROM ocr_comparison_runs c JOIN ocr_ranking_entries r "
                "ON r.uploaded_file_id = c.uploaded_file_id WHERE c.uploaded_file_id = $1",
                file_id,
                key,
            )
        finally:
            await conn.close()

        assert comparison is not None
        assert ranking is not None
        assert tax_id not in str(comparison["original_reading"])
        assert name not in str(comparison["enhanced_reading"])
        assert tax_id not in str(ranking["reading"])
        assert name not in str(ranking["reading"])
        assert all(value is not None for value in comparison[2:])
        assert ranking["counterparty_tax_id"] is not None
        assert ranking["counterparty_name"] is not None
        assert dict(decrypted) == {
            "comparison_tax_id": tax_id,
            "comparison_name": name,
            "ranking_tax_id": tax_id,
            "ranking_name": name,
        }

        # Regresión de auditoría: una contraparte no leída es normal (anti-alucinación). El
        # downgrade no puede convertir los JSONB NOT NULL en SQL NULL al reinsertar esas claves.
        conn = await asyncpg.connect(db_dsn)
        try:
            await conn.execute(
                "UPDATE ocr_comparison_runs SET original_counterparty_tax_id = NULL, "
                "original_counterparty_name = NULL, enhanced_counterparty_tax_id = NULL, "
                "enhanced_counterparty_name = NULL WHERE uploaded_file_id = $1",
                file_id,
            )
            await conn.execute(
                "UPDATE ocr_ranking_entries SET counterparty_tax_id = NULL, "
                "counterparty_name = NULL WHERE uploaded_file_id = $1",
                file_id,
            )
        finally:
            await conn.close()

        await _run_alembic(db_dsn, "downgrade", _PRE_REVISION)

        conn = await asyncpg.connect(db_dsn)
        try:
            comparison_after_downgrade = await conn.fetchrow(
                "SELECT original_reading, enhanced_reading FROM ocr_comparison_runs "
                "WHERE uploaded_file_id = $1",
                file_id,
            )
            ranking_after_downgrade = await conn.fetchrow(
                "SELECT reading FROM ocr_ranking_entries WHERE uploaded_file_id = $1",
                file_id,
            )
        finally:
            await conn.close()

        assert comparison_after_downgrade is not None
        assert ranking_after_downgrade is not None
        assert comparison_after_downgrade["original_reading"] is not None
        assert comparison_after_downgrade["enhanced_reading"] is not None
        assert ranking_after_downgrade["reading"] is not None
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
