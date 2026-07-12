"""Normalización y comparación de razones sociales (dominio puro, sin dependencias externas).

La comparación del nombre leído por el OCR contra la razón social oficial (supplier master o fuente
externa) no puede ser una igualdad de cadenas cruda: el OCR y los registros difieren en mayúsculas y
espaciado. Aquí se normaliza (mayúsculas, espacios colapsados) y se compara de forma determinista.

No se "corrige" el nombre ni se hace fuzzy-matching agresivo: la validación marca, no inventa (S2.8
§4). Un nombre que no casa produce un aviso con la razón social oficial, nunca una corrección
silenciosa.
"""

from __future__ import annotations

__all__ = ["normalize_name", "compare_names"]


def normalize_name(value: str | None) -> str:
    """Forma canónica de una razón social: mayúsculas y espacios internos colapsados.

    Tolera `None` (campo que el OCR no leyó = `null`, regla anti-alucinación): se trata como cadena
    vacía. Colapsa cualquier secuencia de espacios en blanco a uno solo y recorta los extremos, de
    modo que "  Proveedor   SA " y "Proveedor SA" colapsen a la misma clave.
    """
    if value is None:
        return ""
    return " ".join(value.upper().split())


def compare_names(name_read: str | None, official_name: str | None) -> bool | None:
    """Compara el nombre leído contra el oficial de forma normalizada.

    Devuelve `True`/`False` si ambos nombres están presentes; `None` si falta alguno (no se puede
    afirmar ni negar la coincidencia: la pantalla de revisión lo tratará como "sin dato").
    """
    read = normalize_name(name_read)
    official = normalize_name(official_name)
    if not read or not official:
        return None
    return read == official
