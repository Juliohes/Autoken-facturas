"""Guardas comunes de decodificación de imagen para toda la familia de preprocesados de factura
(`ocr.preprocess.enhance`, S2.9; `ocr.preprocess.clahe`, S6.7): comprobación de `content_type`
soportado + tope de píxeles antes de decodificar de verdad.

Módulo neutral (2026-08-11, S6.7 auditoría, hallazgo de arquitectura): `open_bounded_image` vivía
antes dentro de `enhance.py`, que en origen representaba solo UNA variante de preprocesado --
mezclaba dos roles ("soy la variante de contraste/brillo/saturación" + "soy la base compartida de
decodificación de toda la familia"). Ninguna de las dos variantes "posee" a la otra: ambas importan
de aquí de forma simétrica. `enhance.py` sigue reexportando estos nombres para no romper ningún
import ya existente (S2.9/S2.10/S4.8), pero la definición vive solo aquí.

Módulo PURO (sin red, sin I/O de infraestructura): solo decodifica bytes ya en memoria.
"""

from __future__ import annotations

import io

from PIL import Image

__all__ = [
    "SUPPORTED_CONTENT_TYPES",
    "UnsupportedImageError",
    "ImageTooLargeError",
    "open_bounded_image",
]

# Solo imágenes fotografiables: un PDF generado digitalmente no tiene problemas de luz que realzar
# (decisión de dominio, spec S2.9 C3/§6) -- nunca se intenta procesar como si fuera una foto.
SUPPORTED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

# Tope de megapíxeles ANTES de decodificar de verdad (`.load()`): una foto de factura con un móvil
# actual no pasa de unos pocos MP; 40 MP es holgado para eso y muy por debajo del umbral donde
# Pillow solo emite un aviso no bloqueante (`DecompressionBombWarning`, ~89.5 MP por defecto) en vez
# de negarse a decodificar -- auditoría S2.9, hallazgo de seguridad: sin este tope, una imagen
# adversarial de pocos MB en disco pero con dimensiones declaradas enormes puede agotar memoria al
# decodificar.
_MAX_PIXELS = 40_000_000


class UnsupportedImageError(Exception):
    """`content_type` no es una de las imágenes soportadas: no se intenta adivinar ni procesar."""


class ImageTooLargeError(Exception):
    """La imagen declara más píxeles que `_MAX_PIXELS`: se rechaza antes de decodificarla entera."""


def open_bounded_image(content: bytes, content_type: str) -> Image.Image:
    """Decodifica una imagen aplicando las mismas guardas que necesita cualquier preprocesado de
    esta familia (S2.9/S6.7): `content_type` soportado + tope de píxeles ANTES de decodificar de
    verdad (`Image.open` solo lee la cabecera; el coste real está en `.load()`).

    Lanza `UnsupportedImageError` si `content_type` no está en `SUPPORTED_CONTENT_TYPES` (C12).
    Lanza `ImageTooLargeError` si las dimensiones declaradas superan `_MAX_PIXELS`. Ante bytes de
    imagen corruptos de un tipo sí soportado, deja escapar la excepción nativa de Pillow
    (`PIL.UnidentifiedImageError`/`OSError`): el llamador ya trata cualquier fallo de este paso como
    "el preprocesado falló", sin necesitar un tipo propio para eso (C5).
    """
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise UnsupportedImageError(
            f"content_type no soportado para preprocesado: {content_type!r}"
        )

    opened = Image.open(io.BytesIO(content))
    width, height = opened.size
    if width * height > _MAX_PIXELS:
        raise ImageTooLargeError(
            f"Imagen de {width}x{height} ({width * height} píxeles) supera el tope de "
            f"{_MAX_PIXELS} antes de decodificar"
        )
    opened.load()
    return opened
