"""Guarda de empaquetado del paquete `ocr.engines`.

Regresión: `build_claude_engine` estaba en `__all__` pero sin importar, así que
`from ocr.engines import build_claude_engine` (lo que hace el runner del bench) fallaba, y ni
mypy ni los tests lo veían (el runner no está cubierto). Este test cierra ese hueco.
"""

import ocr.engines as engines


def test_todo_lo_exportado_es_importable() -> None:
    """Cada nombre de `__all__` existe de verdad en el paquete (no solo declarado)."""
    faltan = [name for name in engines.__all__ if not hasattr(engines, name)]
    assert not faltan, f"nombres en __all__ sin importar: {faltan}"
