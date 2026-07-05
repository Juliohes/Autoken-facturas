"""Rasteriza un PDF a una imagen PNG por página (paso previo a los motores solo-imagen).

Los motores de visión (gpt) no aceptan PDF; se les manda cada página como PNG. Se usa `pypdfium2`
(motor PDFium, licencia permisiva Apache/BSD, sin binarios de sistema) para renderizar y Pillow
para codificar el PNG. La resolución por defecto (`_DEFAULT_DPI`) es holgada para no perder el
texto pequeño de la factura (CIF/NIF, §11.8).
"""

from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

# 200 DPI: legible el texto pequeño sin inflar el tamaño de la imagen que viaja al proveedor.
_DEFAULT_DPI = 200
# PDFium mide en puntos a 72 DPI; el factor de escala lleva de puntos a píxeles al DPI deseado.
_PDF_POINTS_PER_INCH = 72


class RasterizeError(Exception):
    """El PDF no se pudo rasterizar (corrupto, cifrado o no es realmente un PDF)."""


def rasterize_pdf(path: str | Path, *, dpi: int = _DEFAULT_DPI) -> list[bytes]:
    """Renderiza cada página del PDF y devuelve su PNG en bytes (una entrada por página).

    Lanza `RasterizeError` ante cualquier fallo de la librería nativa: nada crudo cruza la frontera.
    """
    path = Path(path)
    scale = dpi / _PDF_POINTS_PER_INCH
    try:
        document = pdfium.PdfDocument(path)
    except Exception as exc:  # PDF ilegible: no dejamos escapar la excepción nativa
        raise RasterizeError(f"No se pudo abrir el PDF {path.name}: {exc}") from exc

    try:
        pages: list[bytes] = []
        for page in document:
            bitmap = page.render(scale=scale)
            image: Image.Image = bitmap.to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pages.append(buffer.getvalue())
    except Exception as exc:
        raise RasterizeError(f"No se pudo rasterizar el PDF {path.name}: {exc}") from exc
    finally:
        document.close()

    if not pages:
        raise RasterizeError(f"El PDF {path.name} no tiene páginas que rasterizar")
    return pages
