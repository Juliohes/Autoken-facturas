"""Tests del rasterizador de PDF (Capa 2, preprocesado común a los motores solo-imagen).

Comportamiento observable: dado un PDF, devuelve una imagen PNG por página, lista para mandarla
a un motor de visión que no acepta PDF nativo (gpt-visión, issue #16).
"""

from pathlib import Path

import pytest
from PIL import Image

from ocr.preprocess import RasterizeError, rasterize_pdf

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _pdf(tmp_path: Path, pages: int) -> Path:
    """Genera un PDF real de `pages` páginas (con Pillow) para no depender del dataset."""
    imgs = [Image.new("RGB", (200, 280), "white") for _ in range(pages)]
    path = tmp_path / f"factura-{pages}p.pdf"
    imgs[0].save(path, "PDF", save_all=True, append_images=imgs[1:])
    return path


def test_rasteriza_una_imagen_png_por_pagina(tmp_path: Path) -> None:
    paginas = rasterize_pdf(_pdf(tmp_path, pages=2))
    assert len(paginas) == 2
    assert all(png.startswith(_PNG_SIGNATURE) for png in paginas)


def test_un_pdf_de_una_pagina_da_una_sola_imagen(tmp_path: Path) -> None:
    paginas = rasterize_pdf(_pdf(tmp_path, pages=1))
    assert len(paginas) == 1


def test_un_pdf_ilegible_da_error_tipado(tmp_path: Path) -> None:
    """Un PDF corrupto no debe dejar escapar una excepción cruda de la librería nativa."""
    roto = tmp_path / "roto.pdf"
    roto.write_bytes(b"%PDF-1.4 esto no es un PDF valido")
    with pytest.raises(RasterizeError):
        rasterize_pdf(roto)
