"""Guardarraíl estático (sin BD) entre las dos listas de campos escalares puntuables del benchmark
real (S6.7 Área D, auditoría, hallazgo MEDIO de SOLID).

`migrations/versions/0032_benchmark_field_ranking.py::_FIELD_GROUP_CASE` repite a mano el listado
de campos escalares puntuables que ya vive como fuente canónica en
`ocr.benchmark_scoring._SCALAR_FIELD_MATCHERS`. Si algún día se añade un campo puntuable nuevo ahí
(ya ha pasado: `invoice_number` se añadió en S6.1) y nadie actualiza esta migración YA ESCRITA, el
campo nuevo cae en el `CASE ... END` sin ninguna rama que lo capture -> `NULL` -> se filtra en
silencio del ranking agregado, sin error, sin log. Este test falla en rojo el día que eso ocurra.

Mismo patrón estático que `tests/test_migrations.py` (regex sobre el fichero de la migración, sin
importar el módulo ni tocar Postgres): las migraciones de este proyecto son módulos con nombre que
empieza por dígito, no directamente importables con `import`.
"""

from __future__ import annotations

import re
from pathlib import Path

from ocr.benchmark_scoring import _SCALAR_FIELD_MATCHERS

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "versions"
    / "0032_benchmark_field_ranking.py"
)
_CASE_WHEN_FIELD = re.compile(r"WHEN '(\w+)' THEN")


def test_los_campos_del_case_sql_coinciden_con_los_campos_escalares_puntuables() -> None:
    """El conjunto de literales `WHEN '<campo>' THEN` de `_FIELD_GROUP_CASE` (migración 0032) debe
    ser EXACTAMENTE el conjunto de claves de `ocr.benchmark_scoring._SCALAR_FIELD_MATCHERS` -- ni
    un campo puntuable de más (correspondería a un grupo fantasma) ni de menos (correspondería a un
    campo puntuable que se filtra en silencio del ranking agregado, `field_group IS NULL`)."""
    contenido = _MIGRATION_PATH.read_text(encoding="utf-8")
    campos_en_sql = set(_CASE_WHEN_FIELD.findall(contenido))
    campos_puntuables = set(_SCALAR_FIELD_MATCHERS.keys())

    assert campos_en_sql, "no se encontró ningún literal WHEN '...' THEN en la migración 0032"
    assert campos_en_sql == campos_puntuables, (
        "`_FIELD_GROUP_CASE` (migración 0032) ha divergido de "
        "`ocr.benchmark_scoring._SCALAR_FIELD_MATCHERS`: "
        f"solo en el CASE SQL: {campos_en_sql - campos_puntuables}, "
        f"solo en los matchers de Python: {campos_puntuables - campos_en_sql}"
    )
