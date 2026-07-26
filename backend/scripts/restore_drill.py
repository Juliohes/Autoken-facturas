"""CLI del simulacro de restore de un backup cifrado (S5.3).

Uso (desde `backend/`, con el venv activado):
    RESTORE_DRILL_TARGET_DSN="postgresql://postgres:...@host:5432/autoken_restore_drill" \
        python scripts/restore_drill.py --backup-file /ruta/al/backup.enc

`RESTORE_DRILL_TARGET_DSN` (la base de datos NUEVA Y VACÍA donde se restaura, nunca la de origen) se
pasa por variable de entorno, mismo motivo que `BACKUP_DATABASE_ADMIN_DSN` en `backup_database.py`.
La base de datos en sí (vacía, sin tablas de usuario) debe existir de antemano — crearla es una
decisión explícita del operador, fuera de este script (spec §5).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from jobs.restore_drill import (
    RestoreFailedError,
    RestoreTargetNotEmptyError,
    run_restore_drill,
)
from shared.backup_encryption import BackupDecryptionError
from shared.config import get_settings, require_strong_backup_encryption_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backup-file", required=True, type=Path, help="Backup cifrado a restaurar."
    )
    args = parser.parse_args()

    target_dsn = os.environ.get("RESTORE_DRILL_TARGET_DSN")
    if not target_dsn:
        print("Falta RESTORE_DRILL_TARGET_DSN (base de datos destino, vacía).", file=sys.stderr)
        raise SystemExit(2)

    settings = get_settings()
    try:
        require_strong_backup_encryption_key(settings)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    try:
        result = asyncio.run(
            run_restore_drill(args.backup_file, target_dsn, settings.backup_encryption_key)
        )
    except (RestoreTargetNotEmptyError, RestoreFailedError, BackupDecryptionError) as exc:
        print(f"Restore drill fallido: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(
        json.dumps(
            {
                "duration_seconds": round(result.duration_seconds, 2),
                "backup_size_bytes": result.backup_size_bytes,
                "row_counts": result.row_counts,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
