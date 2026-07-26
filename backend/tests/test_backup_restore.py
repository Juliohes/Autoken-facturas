"""Test de comportamiento del backup cifrado + restore drill (S5.3, spec
`docs/specs/S5.3-backups-restore-drill.md`).

Contra Postgres real (fixture `authapi` como origen; una base de datos extra, vacía, creada a mano
como destino del drill) — nunca mocks de `pg_dump`/`pg_restore`. `authapi` ya deja el rol runtime
sembrado; usamos el DSN admin (bypass-RLS) como origen del backup, igual que en producción.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import asyncpg
import httpx
import pytest

from jobs.backup import BackupFailedError, create_encrypted_backup
from jobs.restore_drill import (
    RestoreFailedError,
    RestoreTargetNotEmptyError,
    run_restore_drill,
)
from shared.backup_encryption import BackupDecryptionError
from tests._dbtest import ADMIN_DSN, seed_company, seed_tenant, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]

_ENCRYPTION_KEY = "clave-de-backup-de-prueba-suficientemente-larga-32b"  # gitleaks:allow (test)


async def _create_empty_database() -> str:
    """Crea una base de datos Postgres nueva y completamente vacía (sin migraciones) y devuelve su
    DSN admin. El llamador es responsable de dropearla al terminar."""
    db_name = f"autoken_restore_drill_{uuid4().hex[:12]}"
    root = await asyncpg.connect(f"{ADMIN_DSN}/postgres")
    try:
        await root.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await root.close()
    return f"{ADMIN_DSN}/{db_name}"


async def _drop_database(dsn: str) -> None:
    db_name = dsn.rsplit("/", 1)[-1]
    root = await asyncpg.connect(f"{ADMIN_DSN}/postgres")
    try:
        await root.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
        )
        await root.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await root.close()


async def test_c1_c3_backup_y_restore_reconstruyen_los_datos_exactamente(
    authapi: Api, tmp_path: Path
) -> None:
    _client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "backup-uno", "Backup Uno Asesoria")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Empresa Backupeable SL", cif="A39031620"
    )
    await seed_user(dsns["admin"], tenant_id=tenant_id, email="admin@backup-uno.es")

    backup_path = tmp_path / "backup.enc"
    backup_result = create_encrypted_backup(dsns["admin"], backup_path, _ENCRYPTION_KEY)

    # C1: el fichero final es el cifrado, nunca el volcado en claro.
    assert backup_path.exists()
    assert backup_result.size_bytes == backup_path.stat().st_size
    raw = backup_path.read_bytes()
    assert b"PGDMP" not in raw  # cabecera de un dump `pg_dump --format=custom` sin cifrar

    target_dsn = await _create_empty_database()
    try:
        restore_result = await run_restore_drill(backup_path, target_dsn, _ENCRYPTION_KEY)

        # C6: tiempos reales medidos, no estimados.
        assert backup_result.duration_seconds >= 0
        assert restore_result.duration_seconds >= 0

        # C3: mismos recuentos de filas que el origen, en las tablas que nos importan aquí.
        assert restore_result.row_counts["tenants"] == 1
        assert restore_result.row_counts["companies"] == 1
        assert restore_result.row_counts["users"] == 1

        # C3: la columna cifrada (S5.2) restaura byte a byte idéntica, descifra igual que en origen.
        from shared.config import get_settings
        from shared.encryption import derive_tenant_encryption_key

        key = derive_tenant_encryption_key(get_settings().db_encryption_master_key, tenant_id)
        conn = await asyncpg.connect(target_dsn)
        try:
            decrypted = await conn.fetchval(
                "SELECT pgp_sym_decrypt(cif, $2)::text FROM companies WHERE id = $1",
                company_id,
                key,
            )
        finally:
            await conn.close()
        assert decrypted == "A39031620"
    finally:
        await _drop_database(target_dsn)


async def test_c7_backup_de_una_base_vacia_tambien_restaura(authapi: Api, tmp_path: Path) -> None:
    _client, dsns = authapi  # BD ya migrada, sin ningún tenant/fila de negocio sembrada

    backup_path = tmp_path / "backup-vacio.enc"
    create_encrypted_backup(dsns["admin"], backup_path, _ENCRYPTION_KEY)

    target_dsn = await _create_empty_database()
    try:
        result = await run_restore_drill(backup_path, target_dsn, _ENCRYPTION_KEY)
        assert result.row_counts["tenants"] == 0
        assert "companies" in result.row_counts  # el esquema existe, simplemente sin filas
    finally:
        await _drop_database(target_dsn)


async def test_c2_clave_de_descifrado_incorrecta_falla_de_forma_clara(
    authapi: Api, tmp_path: Path
) -> None:
    _client, dsns = authapi
    backup_path = tmp_path / "backup.enc"
    create_encrypted_backup(dsns["admin"], backup_path, _ENCRYPTION_KEY)

    target_dsn = await _create_empty_database()
    try:
        with pytest.raises(BackupDecryptionError):
            await run_restore_drill(
                backup_path, target_dsn, "otra-clave-completamente-distinta-32b"
            )
    finally:
        await _drop_database(target_dsn)


async def test_c2_fichero_de_backup_truncado_falla_de_forma_clara(
    authapi: Api, tmp_path: Path
) -> None:
    _client, dsns = authapi
    backup_path = tmp_path / "backup.enc"
    create_encrypted_backup(dsns["admin"], backup_path, _ENCRYPTION_KEY)
    backup_path.write_bytes(backup_path.read_bytes()[:20])  # trunca el fichero cifrado

    target_dsn = await _create_empty_database()
    try:
        with pytest.raises(BackupDecryptionError):
            await run_restore_drill(backup_path, target_dsn, _ENCRYPTION_KEY)
    finally:
        await _drop_database(target_dsn)


async def test_c4_restore_drill_rechaza_una_base_destino_con_datos(
    authapi: Api, tmp_path: Path
) -> None:
    _client, dsns = authapi
    backup_path = tmp_path / "backup.enc"
    create_encrypted_backup(dsns["admin"], backup_path, _ENCRYPTION_KEY)

    # El propio origen ya migrado (con tablas) sirve como "destino no vacío" para este caso límite.
    with pytest.raises(RestoreTargetNotEmptyError):
        await run_restore_drill(backup_path, dsns["admin"], _ENCRYPTION_KEY)


async def test_c4_restore_drill_rechaza_datos_en_un_schema_que_no_es_public(
    authapi: Api, tmp_path: Path
) -> None:
    """El chequeo de "vacía" mira TODOS los schemas de usuario, no solo `public` (hallazgo de
    auditoría): una base con datos reales en otro schema no debe pasar por vacía."""
    _client, dsns = authapi
    backup_path = tmp_path / "backup.enc"
    create_encrypted_backup(dsns["admin"], backup_path, _ENCRYPTION_KEY)

    target_dsn = await _create_empty_database()
    try:
        conn = await asyncpg.connect(target_dsn)
        try:
            await conn.execute("CREATE SCHEMA legacy")
            await conn.execute("CREATE TABLE legacy.datos_reales (id int)")
        finally:
            await conn.close()

        with pytest.raises(RestoreTargetNotEmptyError):
            await run_restore_drill(backup_path, target_dsn, _ENCRYPTION_KEY)
    finally:
        await _drop_database(target_dsn)


async def test_c5_backup_fallido_no_deja_fichero_parcial_en_la_ruta_final(tmp_path: Path) -> None:
    output_path = tmp_path / "backup.enc"
    output_path.write_bytes(b"contenido-de-un-backup-bueno-anterior")

    bad_dsn = "postgresql://usuario-que-no-existe:mal@localhost:5433/basequenoexiste"
    with pytest.raises(BackupFailedError):
        create_encrypted_backup(bad_dsn, output_path, _ENCRYPTION_KEY)

    # El backup bueno anterior sigue intacto: el fallo no lo pisó con un fichero parcial/corrupto.
    assert output_path.read_bytes() == b"contenido-de-un-backup-bueno-anterior"
    assert list(tmp_path.glob("*.tmp")) == []


async def test_c5_restore_fallido_por_backup_corrupto_da_error_claro(
    authapi: Api, tmp_path: Path
) -> None:
    _client, dsns = authapi
    # Un fichero "cifrado" que en realidad es basura aleatoria de la longitud correcta: pasa la
    # comprobación de longitud mínima pero pg_restore recibe basura, no un dump válido.
    import os

    from shared.backup_encryption import encrypt_backup

    fake_backup = tmp_path / "backup-corrupto.enc"
    fake_backup.write_bytes(encrypt_backup(_ENCRYPTION_KEY, os.urandom(200)))

    target_dsn = await _create_empty_database()
    try:
        with pytest.raises(RestoreFailedError):
            await run_restore_drill(fake_backup, target_dsn, _ENCRYPTION_KEY)
    finally:
        await _drop_database(target_dsn)
