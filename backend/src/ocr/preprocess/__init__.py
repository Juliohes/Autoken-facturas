"""Preprocesado común de documentos (Capa 2 del pipeline OCR).

Pasos previos a la lectura que comparten varios motores. Hoy: rasterizar el PDF a imágenes para
los motores de visión que no aceptan PDF nativo (gpt-visión, issue #16).
"""

from ocr.preprocess.enhance import (
    ENHANCED_CONTENT_TYPE,
    SUPPORTED_CONTENT_TYPES,
    ImageTooLargeError,
    UnsupportedImageError,
    enhance_invoice_image,
)
from ocr.preprocess.rasterize import RasterizeError, rasterize_pdf

__all__ = [
    "RasterizeError",
    "rasterize_pdf",
    "SUPPORTED_CONTENT_TYPES",
    "ENHANCED_CONTENT_TYPE",
    "UnsupportedImageError",
    "ImageTooLargeError",
    "enhance_invoice_image",
]
