"""Tests de comportamiento S6.7 §5.1: preprocesado CLAHE (contraste local adaptativo), spec
docs/specs/S6.7-benchmark-real-motor-variante.md, la 3ª variante de imagen del benchmark.

Módulo puro (`ocr.preprocess.clahe`): sin red, sin Postgres. Mismo criterio de guardas que
`ocr.preprocess.enhance` (S2.9) -- mismo conjunto de content-types soportados y mismo tope de
píxeles antes de decodificar, reutilizados desde ahí (no duplicados) para no repetir el mismo
hallazgo de seguridad (decompression bomb) en un segundo módulo. Imágenes de prueba generadas con
Pillow, no se depende de facturas reales.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from ocr.preprocess.clahe import CLAHE_CONTENT_TYPE, clahe_invoice_image
from ocr.preprocess.enhance import (
    SUPPORTED_CONTENT_TYPES,
    ImageTooLargeError,
    UnsupportedImageError,
)


def _image_bytes(*, fmt: str, size: tuple[int, int] = (120, 80)) -> bytes:
    """Imagen real (no un mock) con algo de contraste para que el realce sea observable."""
    image = Image.new("RGB", size, "white")
    for x in range(0, size[0], 10):
        for y in range(size[1]):
            image.putpixel((x, y), (60, 60, 60))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "content_type,fmt",
    [("image/jpeg", "JPEG"), ("image/png", "PNG"), ("image/webp", "WEBP")],
)
def test_aplica_clahe_a_una_imagen_soportada(content_type: str, fmt: str) -> None:
    """Imagen soportada -> bytes distintos, decodificables, mismas dimensiones que el original."""
    original = _image_bytes(fmt=fmt)

    result = clahe_invoice_image(original, content_type)

    assert result != original
    decoded = Image.open(io.BytesIO(result))
    decoded.load()
    original_decoded = Image.open(io.BytesIO(original))
    assert decoded.size == original_decoded.size
    assert decoded.mode in ("RGB", "L")  # nunca un canal alfa/paleta colado sin querer


def test_siempre_devuelve_el_content_type_de_clahe_sin_importar_el_de_entrada() -> None:
    result = clahe_invoice_image(_image_bytes(fmt="JPEG"), "image/jpeg")
    decoded = Image.open(io.BytesIO(result))
    assert decoded.format == "PNG"


def test_reutiliza_exactamente_el_mismo_conjunto_de_content_types_que_enhance() -> None:
    """Mismo criterio de dominio que S2.9: solo fotos, nunca un PDF (fuente única de verdad, no
    una segunda lista que pueda desincronizarse de la de `enhance.py`)."""
    assert {"image/jpeg", "image/png", "image/webp"} == SUPPORTED_CONTENT_TYPES


def test_content_type_no_soportado_lanza_el_mismo_error_tipado_que_enhance() -> None:
    with pytest.raises(UnsupportedImageError):
        clahe_invoice_image(b"%PDF-1.4 no es una imagen", "application/pdf")


def test_imagen_con_demasiados_pixeles_se_rechaza_antes_de_decodificar() -> None:
    """Mismo hallazgo de seguridad que S2.9 (decompression bomb) -- CLAHE parte SIEMPRE del
    fichero original (spec §5.1, nunca de una versión ya reducida), así que necesita la MISMA
    guarda, no una copia que alguien podría olvidar mantener sincronizada."""
    grande = Image.new("L", (6400, 6300), 128)  # 40.32M píxeles, por encima del tope de 40M.
    buffer = io.BytesIO()
    grande.save(buffer, format="PNG")

    with pytest.raises(ImageTooLargeError):
        clahe_invoice_image(buffer.getvalue(), "image/png")


def test_clahe_content_type_es_png_como_enhance() -> None:
    assert CLAHE_CONTENT_TYPE == "image/png"
