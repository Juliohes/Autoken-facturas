"""Validación estructural acotada de JPEG/PNG no confiables (S6.13)."""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError


class InvalidImage(ValueError):
    """La imagen no se puede decodificar de forma segura."""


def validate_image(content: bytes, content_type: str, *, max_pixels: int) -> None:
    """Comprueba formato, dimensiones y carga completa antes de almacenar una imagen."""
    expected_format = {"image/jpeg": "JPEG", "image/png": "PNG"}.get(content_type)
    if expected_format is None:
        return
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != expected_format:
                raise InvalidImage
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > max_pixels:
                raise InvalidImage
            image.verify()
        # ``verify`` invalida el decodificador; abrir de nuevo y cargar detecta JPEG truncados.
        with Image.open(io.BytesIO(content)) as image:
            image.load()
    except (Image.DecompressionBombError, OSError, SyntaxError, UnidentifiedImageError) as exc:
        raise InvalidImage from exc
