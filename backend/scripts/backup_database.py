"""CLI del backup completo cifrado de la base de datos (S5.3).

Uso (desde `backend/`, con el venv activado):
    BACKUP_DATABASE_ADMIN_DSN="postgresql://postgres:...@host:5432/autoken" \
        python scripts/backup_database.py --output /ruta/al/backup.enc

`BACKUP_DATABASE_ADMIN_DSN` (DSN con privilegios de superusuario/bypass-RLS, el mismo tipo de
credencial que ya usan las migraciones de Alembic y `rotate_encryption_key.py`) se pasa SIEMPRE por
variable de entorno, nunca por argumento de línea de comandos: un argumento de CLI queda visible en
`ps`/el historial de shell (mismo hallazgo de auditoría que la clave de rotación de S5.2).

La clave de cifrado del backup se lee de `Settings.backup_encryption_key`
(`BACKUP_ENCRYPTION_KEY`), nunca de un argumento.

En producción, este script se ejecuta por cron (fuera de alcance de esta tarea, ver
`docs/runbooks/backups-restore.md`) apuntando `--output` a una ruta que luego se sube a un destino
externo real (Hetzner u otro, también pendiente — ver el mismo runbook).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from jobs.backup import BackupFailedError, create_encrypted_backup
from shared.config import get_settings, require_strong_backup_encryption_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Ruta del backup cifrado.")
    args = parser.parse_args()

    database_url = os.environ.get("BACKUP_DATABASE_ADMIN_DSN")
    if not database_url:
        print("Falta BACKUP_DATABASE_ADMIN_DSN (DSN admin de origen).", file=sys.stderr)
        raise SystemExit(2)

    settings = get_settings()
    try:
        require_strong_backup_encryption_key(settings)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    try:
        result = create_encrypted_backup(database_url, args.output, settings.backup_encryption_key)
    except BackupFailedError as exc:
        print(f"Backup fallido: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(
        f"Backup escrito en {result.output_path} "
        f"({result.size_bytes} bytes, {result.duration_seconds:.2f}s)."
    )


if __name__ == "__main__":
    main()
