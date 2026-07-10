"""Introspección de violaciones de UNIQUE para el patrón "pre-check + captura de carrera" (TOCTOU).

Cuando dos peticiones concurrentes esquivan un pre-check de unicidad (SELECT), ambas llegan al
INSERT y una viola el UNIQUE. Para reabsorber la carrera hay que distinguir QUÉ restricción se violó
(y no enmascarar otra violación de integridad como si fuera el duplicado esperado). El nombre de la
restricción lo expone el error nativo de asyncpg (`constraint_name`), que SQLAlchemy envuelve.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError


def violates_unique_constraint(exc: IntegrityError, constraint_name: str) -> bool:
    """True si la `IntegrityError` procede del UNIQUE `constraint_name` (y no de otra restricción).

    Se recorre la cadena de causas (`__cause__`) hasta encontrar el `constraint_name` que expone
    asyncpg. Distinguir la restricción evita traducir cualquier otra violación de integridad como si
    fuera el duplicado esperado.
    """
    current: BaseException | None = exc
    while current is not None:
        if getattr(current, "constraint_name", None) == constraint_name:
            return True
        current = current.__cause__
    return False
