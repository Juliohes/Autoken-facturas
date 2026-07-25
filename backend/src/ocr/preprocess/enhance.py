"""Realce de imagen de una factura (S2.9): más contraste, brillo y saturación antes del lector.

Módulo PURO (sin red, sin I/O de infraestructura): solo transforma bytes de imagen con Pillow. Nunca
se persiste en MinIO ni se le enseña al usuario (es un insumo efímero de la comparativa de S2.10).
Es una función SÍNCRONA y con coste de CPU/memoria real (decodificar + 3 realces + codificar PNG):
el llamador (`jobs.ocr`) es responsable de invocarla con `asyncio.to_thread`, igual que ya hace con
la descarga de MinIO, para no bloquear el event loop del worker (auditoría, hallazgo de patrones).

Los parámetros son conservadores y pensados para fotos de móvil con poca luz (el caso que motiva la
tarea, S2.2): un realce agresivo puede "quemar" el detalle fino (un dígito de un CIF, un céntimo de
un importe) en vez de ayudar al lector. NO se han afinado empíricamente contra el bench real de
20 facturas — eso exige llamadas de pago a la API y queda fuera de esta tarea (spec §6); estas
constantes son el único punto de ajuste cuando Julio decida invertir ese presupuesto.
"""

from __future__ import annotations

import io

from PIL import Image, ImageEnhance

__all__ = [
    "SUPPORTED_CONTENT_TYPES",
    "ENHANCED_CONTENT_TYPE",
    "UnsupportedImageError",
    "ImageTooLargeError",
    "enhance_invoice_image",
]

# Solo imágenes fotografiables: un PDF generado digitalmente no tiene problemas de luz que realzar
# (decisión de dominio, spec C3/§6) — nunca se intenta procesar como si fuera una foto.
SUPPORTED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
# El realce siempre produce PNG, cualquiera que sea el formato de entrada (fuente única de verdad
# para quien necesite reconocer una lectura "de la imagen realzada" por su content-type, p. ej. el
# doble de test `tests/_ocr.py::make_comparison_extractor`).
ENHANCED_CONTENT_TYPE = "image/png"

_CONTRAST = 1.25
_BRIGHTNESS = 1.10
_SATURATION = 1.15

# Tope de megapíxeles ANTES de decodificar de verdad (`.load()`): una foto de factura con un móvil
# actual no pasa de unos pocos MP; 40 MP es holgado para eso y muy por debajo del umbral donde
# Pillow solo emite un aviso no bloqueante (`DecompressionBombWarning`, ~89.5 MP por defecto) en vez
# de negarse a decodificar — auditoría, hallazgo de seguridad: sin este tope, una imagen adversarial
# de pocos MB en disco pero con dimensiones declaradas enormes puede agotar memoria al decodificar.
_MAX_PIXELS = 40_000_000


class UnsupportedImageError(Exception):
    """`content_type` no es una de las imágenes soportadas: no se intenta adivinar ni procesar."""


class ImageTooLargeError(Exception):
    """La imagen declara más píxeles que `_MAX_PIXELS`: se rechaza antes de decodificarla entera."""


def enhance_invoice_image(content: bytes, content_type: str) -> bytes:
    """Aplica contraste + brillo + saturación moderados; devuelve siempre `ENHANCED_CONTENT_TYPE`.

    Lanza `UnsupportedImageError` si `content_type` no está en `SUPPORTED_CONTENT_TYPES` (C12).
    Lanza `ImageTooLargeError` si las dimensiones declaradas superan `_MAX_PIXELS`, ANTES de
    decodificar el resto de la imagen (`Image.open` solo lee la cabecera; el coste real está en
    `.load()`). Ante bytes de imagen corruptos de un tipo sí soportado, deja escapar la excepción
    nativa de Pillow (`PIL.UnidentifiedImageError`/`OSError`): el llamador (comparativa, S2.10) ya
    trata cualquier fallo de este paso como "la comparativa falló", sin necesitar un tipo propio
    para eso (C5). Síncrona y con coste real de CPU/memoria: ver nota del módulo sobre `to_thread`.
    """
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise UnsupportedImageError(f"content_type no soportado para realce: {content_type!r}")

    opened = Image.open(io.BytesIO(content))
    width, height = opened.size
    if width * height > _MAX_PIXELS:
        raise ImageTooLargeError(
            f"Imagen de {width}x{height} ({width * height} píxeles) supera el tope de "
            f"{_MAX_PIXELS} antes de decodificar"
        )
    opened.load()
    image: Image.Image = opened
    image = ImageEnhance.Contrast(image).enhance(_CONTRAST)
    image = ImageEnhance.Brightness(image).enhance(_BRIGHTNESS)
    image = ImageEnhance.Color(image).enhance(_SATURATION)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
