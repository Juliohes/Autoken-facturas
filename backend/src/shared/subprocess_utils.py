"""Helper compartido para invocar un subproceso externo y fallar alto y claro (S5.3).

Extraído de `jobs/backup.py`/`jobs/restore_drill.py` (mismo patrón "lista de argumentos fija, nunca
`shell=True`, código de salida != 0 -> excepción con `stderr`" duplicado en ambos).
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from shared.pg_dsn import redact_dsn


def run_checked(
    args: Sequence[str],
    exception_cls: type[Exception],
    *,
    input: bytes | None = None,  # noqa: A002 (mismo nombre que `subprocess.run`, más claro así)
    env: dict[str, str] | None = None,
    timeout_seconds: float = 1800,
) -> bytes:
    """Ejecuta `args` y devuelve su `stdout`. Código de salida != 0 o timeout -> `exception_cls`
    con `stderr` (con cualquier credencial de estilo URL redactada, ver `shared.pg_dsn.redact_dsn`:
    algunas versiones de `pg_dump`/`pg_restore` repiten el DSN completo en su propio error)."""
    try:
        result = subprocess.run(  # noqa: S603 (lista de argumentos fija, sin shell)
            list(args),
            input=input,
            capture_output=True,
            env=env,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise exception_cls(f"{args[0]} no terminó en {timeout_seconds:.0f}s (timeout).") from exc

    if result.returncode != 0:
        stderr = redact_dsn(result.stderr.decode("utf-8", errors="replace"))
        raise exception_cls(f"{args[0]} terminó con código {result.returncode}: {stderr}")
    return result.stdout
