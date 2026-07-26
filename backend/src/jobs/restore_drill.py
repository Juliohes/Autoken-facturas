"""Simulacro de restore de un backup cifrado (S5.3).

Ver spec `docs/specs/S5.3-backups-restore-drill.md`. Descifra un backup
(`shared/backup_encryption.py`) y lo restaura con `pg_restore` en una base de datos NUEVA Y VACÍA —
nunca la de origen. Antes de tocarla, comprueba que de verdad está vacía (C4): un simulacro apuntado
por error a una base con datos reales nunca la sobrescribe en silencio.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import structlog

from shared.backup_encryption import decrypt_backup
from shared.pg_dsn import to_libpq_dsn, to_pg_cli_args
from shared.subprocess_utils import run_checked

logger = structlog.get_logger("jobs.restore_drill")

# Schemas de sistema de Postgres, nunca datos de negocio: se excluyen del chequeo de "base de datos
# vacía" (C4) para no confundir el propio esquema interno de Postgres con datos reales.
_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


class RestoreTargetNotEmptyError(Exception):
    """La base de datos destino ya tiene tablas de usuario: el drill se niega a tocarla."""


class RestoreFailedError(Exception):
    """`pg_restore` terminó con un código de salida distinto de cero, o no respondió a tiempo."""


@dataclass(frozen=True)
class RestoreResult:
    duration_seconds: float
    backup_size_bytes: int
    row_counts: dict[str, int]


async def _assert_target_is_empty(database_url: str) -> None:
    conn = await asyncpg.connect(dsn=to_libpq_dsn(database_url))
    try:
        # TODOS los schemas de usuario, no solo `public`: una base con tablas reales en otro
        # schema no debe pasar por "vacía" (C4) solo porque `public` esté limpio.
        count = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema != ALL($1::text[])",
            list(_SYSTEM_SCHEMAS),
        )
    finally:
        await conn.close()
    if count:
        raise RestoreTargetNotEmptyError(
            f"La base de datos destino ya tiene {count} tabla(s) de usuario: el restore drill "
            "solo se ejecuta contra una base de datos nueva y vacía, para no sobrescribir datos "
            "reales por error."
        )


async def _row_counts(database_url: str) -> dict[str, int]:
    conn = await asyncpg.connect(dsn=to_libpq_dsn(database_url))
    try:
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        counts: dict[str, int] = {}
        for row in tables:
            table = row["tablename"]
            counts[table] = await conn.fetchval(f'SELECT count(*) FROM "{table}"')  # noqa: S608
        return counts
    finally:
        await conn.close()


def _run_pg_restore(target_database_url: str, dump: bytes, *, timeout_seconds: float) -> None:
    args, pg_env = to_pg_cli_args(target_database_url)
    run_checked(
        ["pg_restore", *args, "--clean", "--if-exists", "--no-owner", "--no-privileges"],
        RestoreFailedError,
        input=dump,
        env={**os.environ, **pg_env},
        timeout_seconds=timeout_seconds,
    )


async def run_restore_drill(
    backup_path: Path,
    target_database_url: str,
    encryption_key: str,
    *,
    timeout_seconds: float = 1800,
) -> RestoreResult:
    """Restaura `backup_path` (cifrado) en `target_database_url` (nueva y vacía) y mide el tiempo.

    Lanza `BackupDecryptionError` (clave incorrecta/fichero corrupto), `RestoreTargetNotEmptyError`
    (destino no vacío, C4) o `RestoreFailedError` (`pg_restore` falló) — nunca deja el destino a
    medio restaurar sin avisar.
    """
    await _assert_target_is_empty(target_database_url)

    encrypted = Path(backup_path).read_bytes()
    dump = decrypt_backup(encryption_key, encrypted)

    start = time.monotonic()
    try:
        _run_pg_restore(target_database_url, dump, timeout_seconds=timeout_seconds)
    except RestoreFailedError:
        logger.error("restore_drill.failed", backup_path=str(backup_path))
        raise
    duration = time.monotonic() - start

    counts = await _row_counts(target_database_url)
    logger.info(
        "restore_drill.done",
        backup_path=str(backup_path),
        duration_seconds=duration,
        row_counts=counts,
    )
    return RestoreResult(
        duration_seconds=duration, backup_size_bytes=len(encrypted), row_counts=counts
    )
