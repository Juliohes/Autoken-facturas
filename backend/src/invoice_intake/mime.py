"""Detección del MIME **real** de un fichero por su número mágico (bytes), no por el declarado.

La decisión de aceptar/rechazar el tipo se toma SOLO con estos bytes (spec S2.1 §2, C3/C4): ni la
extensión del nombre ni la cabecera `Content-Type` que manda el cliente cambian el veredicto. Un
ejecutable renombrado a `.jpg` con `Content-Type: image/jpeg` se detecta por lo que es y se rechaza.
"""

from __future__ import annotations

import filetype

# Tipos admitidos en el intake (spec S2.1 §2): imagen de factura o PDF. Cualquier otro MIME real ->
# 415. HEIC y demás formatos de móvil quedan fuera de alcance (los normaliza la captura S2.2).
ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "application/pdf"})


def sniff_mime(content: bytes) -> str | None:
    """MIME real deducido de los bytes (número mágico), o `None` si no se reconoce.

    Delega en `filetype.guess`, que lee solo la cabecera. Un fichero vacío o de tipo desconocido
    devuelve `None`; el llamante decide el código (vacío -> 422, tipo no admitido -> 415).
    """
    kind = filetype.guess(content)
    return kind.mime if kind is not None else None


def is_allowed(mime: str | None) -> bool:
    """True si el MIME real está en la allowlist del intake (jpeg/png/pdf)."""
    return mime in ALLOWED_MIME_TYPES
