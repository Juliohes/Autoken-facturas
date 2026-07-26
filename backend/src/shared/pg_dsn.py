"""Utilidades de DSN para invocar `pg_dump`/`pg_restore` (S5.3) sin filtrar la contraseña.

Un DSN completo (`postgresql://usuario:contraseña@host/bd`) pasado como argumento posicional a un
subproceso queda visible en `ps`/`/proc/<pid>/cmdline` mientras el proceso vive — el mismo riesgo
que la spec S5.3 §4 exige evitar para `BACKUP_ENCRYPTION_KEY`, aplicado aquí también al DSN admin.
`to_pg_cli_args` descompone el DSN en flags sin contraseña + un `PGPASSWORD` para el entorno del
subproceso (solo visible en `/proc/<pid>/environ`, no en `ps`).
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

_CREDENTIALS_IN_URL = re.compile(r"://[^:/@]+:[^@/]*@")


def to_libpq_dsn(database_url: str) -> str:
    """Convierte un DSN estilo SQLAlchemy/asyncpg (`postgresql+asyncpg://...`) al formato que
    entienden `pg_dump`/`pg_restore` (`postgresql://...`)."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def to_pg_cli_args(database_url: str) -> tuple[list[str], dict[str, str]]:
    """Descompone un DSN en argumentos de `pg_dump`/`pg_restore` SIN la contraseña, más un entorno
    con `PGPASSWORD` para pasársela al subproceso por variable de entorno."""
    parsed = urlsplit(to_libpq_dsn(database_url))
    args = ["-h", parsed.hostname or "localhost"]
    if parsed.port:
        args += ["-p", str(parsed.port)]
    if parsed.username:
        args += ["-U", unquote(parsed.username)]
    dbname = parsed.path.lstrip("/")
    if dbname:
        args += ["-d", dbname]
    env = {"PGPASSWORD": unquote(parsed.password)} if parsed.password else {}
    return args, env


def redact_dsn(text: str) -> str:
    """Sustituye cualquier `usuario:contraseña@` de estilo URL por `***:***@` en `text`.

    Defensa en profundidad: algunas versiones de `pg_dump`/`pg_restore` repiten el DSN completo
    (con contraseña) dentro de su propio mensaje de error ante un DSN malformado (verificado
    empíricamente). Se aplica siempre a `stderr` antes de incluirlo en una excepción, nunca se
    confía en que la herramienta externa no vaya a filtrar el secreto.
    """
    return _CREDENTIALS_IN_URL.sub("://***:***@", text)
