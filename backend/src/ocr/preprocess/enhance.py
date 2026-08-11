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

`SUPPORTED_CONTENT_TYPES`/`UnsupportedImageError`/`ImageTooLargeError`/`open_bounded_image` viven
ahora en `ocr.preprocess._guards` (2026-08-11, S6.7 auditoría, hallazgo de arquitectura: son la base
compartida de decodificación de TODA la familia de preprocesados, no solo de esta variante) --
reexportados aquí sin cambio de comportamiento para no romper ningún import existente (S2.9/S2.10/
S4.8/`jobs.ocr`).
"""

from __future__ import annotations

import io

from PIL import Image, ImageEnhance

from ocr.preprocess._guards import (
    SUPPORTED_CONTENT_TYPES,
    ImageTooLargeError,
    UnsupportedImageError,
    open_bounded_image,
)

__all__ = [
    "SUPPORTED_CONTENT_TYPES",
    "ENHANCED_CONTENT_TYPE",
    "UnsupportedImageError",
    "ImageTooLargeError",
    "enhance_invoice_image",
    "open_bounded_image",
]

# El realce siempre produce PNG, cualquiera que sea el formato de entrada (fuente única de verdad
# para quien necesite reconocer una lectura "de la imagen realzada" por su content-type, p. ej. el
# doble de test `tests/_ocr.py::make_comparison_extractor`).
ENHANCED_CONTENT_TYPE = "image/png"

_CONTRAST = 1.25
_BRIGHTNESS = 1.10
_SATURATION = 1.15


def enhance_invoice_image(content: bytes, content_type: str) -> bytes:
    """Aplica contraste + brillo + saturación moderados; devuelve siempre `ENHANCED_CONTENT_TYPE`.

    Lanza `UnsupportedImageError`/`ImageTooLargeError` vía `open_bounded_image` (ver ahí el detalle
    de cada guarda). Síncrona y con coste real de CPU/memoria: ver nota del módulo sobre
    `to_thread`.
    """
    image: Image.Image = open_bounded_image(content, content_type)
    image = ImageEnhance.Contrast(image).enhance(_CONTRAST)
    image = ImageEnhance.Brightness(image).enhance(_BRIGHTNESS)
    image = ImageEnhance.Color(image).enhance(_SATURATION)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
