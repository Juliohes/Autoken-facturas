"""Tests de comportamiento S2.9: realce de imagen (spec docs/specs/S2.9-S2.10-preprocesado-*.md).

Criterios C11, C12. Módulo puro (`ocr.preprocess.enhance`): sin red, sin Postgres, sin MinIO. Las
imágenes de prueba se generan con Pillow, no se depende de facturas reales del dataset.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from ocr.preprocess.enhance import (
    SUPPORTED_CONTENT_TYPES,
    ImageTooLargeError,
    UnsupportedImageError,
    enhance_invoice_image,
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
def test_c11_realza_una_imagen_soportada(content_type: str, fmt: str) -> None:
    """C11: imagen soportada -> bytes distintos, decodificables, mismas dimensiones."""
    original = _image_bytes(fmt=fmt)

    enhanced = enhance_invoice_image(original, content_type)

    assert enhanced != original
    decoded = Image.open(io.BytesIO(enhanced))
    decoded.load()
    original_decoded = Image.open(io.BytesIO(original))
    assert decoded.size == original_decoded.size


def test_c11_content_types_soportados_son_solo_imagenes_de_foto() -> None:
    """C11/C3: el conjunto soportado es exactamente el de imágenes fotografiables (no PDF)."""
    assert {"image/jpeg", "image/png", "image/webp"} == SUPPORTED_CONTENT_TYPES


def test_c12_content_type_no_soportado_lanza_error_tipado() -> None:
    """C12: un `content_type` no soportado (p. ej. PDF) nunca se procesa como si fuera una foto."""
    with pytest.raises(UnsupportedImageError):
        enhance_invoice_image(b"%PDF-1.4 no es una imagen", "application/pdf")


def test_c12_no_intenta_adivinar_un_content_type_desconocido() -> None:
    """C12: un tipo desconocido cualquiera también se rechaza explícitamente, nunca en silencio."""
    with pytest.raises(UnsupportedImageError):
        enhance_invoice_image(_image_bytes(fmt="PNG"), "image/tiff")


def test_c12_imagen_con_demasiados_pixeles_se_rechaza_antes_de_decodificar() -> None:
    """C12 (hallazgo de seguridad de la auditoría): dimensiones adversariales -> error tipado,
    nunca decodificación completa (vector de decompression bomb)."""
    grande = Image.new("L", (6400, 6300), 128)  # 40.32M píxeles, por encima del tope de 40M.
    buffer = io.BytesIO()
    grande.save(buffer, format="PNG")

    with pytest.raises(ImageTooLargeError):
        enhance_invoice_image(buffer.getvalue(), "image/png")
