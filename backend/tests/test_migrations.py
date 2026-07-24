"""Guardarraíles estáticos sobre `migrations/versions/` (sin BD): errores de forma que romperían
`alembic upgrade head` de verdad, no solo en este proyecto sino en cualquier entorno.

Nace de un hallazgo real de una auditoría (cierre de S4.6, 2026-07-24): el `revision` de la
migración 0014 tenía 40 caracteres, por encima del límite de `alembic_version.version_num`
(`varchar(32)`, default de Alembic sin override en `env.py`) — habría reventado cualquier
`alembic upgrade head` real con `StringDataRightTruncationError`, y con él toda la suite de tests
que aprovisiona BD (`provision_test_db()`). Nadie lo detectó hasta una auditoría manual porque
ningún test lo comprobaba.
"""

from __future__ import annotations

import re
from pathlib import Path

_VERSIONS_DIR = Path(__file__).resolve().parent.parent / "migrations" / "versions"
_MAX_REVISION_LENGTH = 32  # `alembic_version.version_num`, varchar(32) por defecto de Alembic.
_REVISION_ASSIGNMENT = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def test_migrations_revision_id_cabe_en_alembic_version() -> None:
    """Ningún `revision` de ninguna migración supera `alembic_version.version_num` (32 chars)."""
    demasiado_largos = []
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        match = _REVISION_ASSIGNMENT.search(path.read_text(encoding="utf-8"))
        assert match is not None, f"{path.name}: no se encontró la asignación de `revision`"
        revision_id = match.group(1)
        if len(revision_id) > _MAX_REVISION_LENGTH:
            demasiado_largos.append((path.name, revision_id, len(revision_id)))

    assert not demasiado_largos, (
        f"revision id(s) por encima de {_MAX_REVISION_LENGTH} caracteres "
        f"(rompería `alembic upgrade head`): {demasiado_largos}"
    )
