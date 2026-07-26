"""Backup completo cifrado de la base de datos (S5.3).

Ver spec `docs/specs/S5.3-backups-restore-drill.md`. Vuelca TODA la base compartida (ADR-0001: una
sola base, aislamiento por RLS) con `pg_dump`, cifra el volcado en memoria (nunca lo escribe en
claro en disco, C1) y lo escribe de forma atómica: fichero temporal de nombre único en el mismo
directorio + `os.replace` solo tras un cifrado completo con éxito (C5) — un fallo a mitad de camino,
o dos ejecuciones solapadas del cron, nunca dejan un backup parcial/corrupto en la ruta final.

`database_url` debe ser un DSN con privilegios de superusuario/bypass-RLS (el mismo que ya usan las
migraciones de Alembic y la rotación de clave de S5.2): con el rol runtime restringido, RLS le
ocultaría casi todas las filas de casi todos los tenants.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import structlog

from shared.backup_encryption import encrypt_backup
from shared.pg_dsn import to_pg_cli_args
from shared.subprocess_utils import run_checked

logger = structlog.get_logger("jobs.backup")


class BackupFailedError(Exception):
    """`pg_dump` terminó con un código de salida distinto de cero, o no respondió a tiempo."""


@dataclass(frozen=True)
class BackupResult:
    output_path: Path
    size_bytes: int
    duration_seconds: float


def _run_pg_dump(database_url: str, *, timeout_seconds: float) -> bytes:
    args, pg_env = to_pg_cli_args(database_url)
    return run_checked(
        ["pg_dump", *args, "--format=custom", "--no-owner", "--no-privileges"],
        BackupFailedError,
        env={**os.environ, **pg_env},
        timeout_seconds=timeout_seconds,
    )


def create_encrypted_backup(
    database_url: str, output_path: Path, encryption_key: str, *, timeout_seconds: float = 1800
) -> BackupResult:
    """Genera un backup completo cifrado en `output_path`. Ver docstring del módulo."""
    start = time.monotonic()
    try:
        dump = _run_pg_dump(database_url, timeout_seconds=timeout_seconds)
        encrypted = encrypt_backup(encryption_key, dump)

        output_path = Path(output_path)
        # Sufijo único (no un `.tmp` fijo): dos ejecuciones solapadas del cron (p. ej. un `pg_dump`
        # colgado de la anterior) nunca escriben al mismo fichero temporal ni se pisan entre sí.
        tmp_path = output_path.with_name(f"{output_path.name}.{uuid4().hex}.tmp")
        tmp_path.write_bytes(encrypted)
        tmp_path.replace(output_path)  # atómico dentro del mismo filesystem (C5)
    except BackupFailedError:
        logger.error("backup.failed", output_path=str(output_path))
        raise

    duration = time.monotonic() - start
    logger.info(
        "backup.done",
        output_path=str(output_path),
        size_bytes=len(encrypted),
        duration_seconds=duration,
    )
    return BackupResult(
        output_path=output_path, size_bytes=len(encrypted), duration_seconds=duration
    )
