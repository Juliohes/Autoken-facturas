"""Adaptadores de motores OCR para el bench.

Cada motor (cloud o self-hosted) implementa el protocolo :class:`OcrEngine`: recibe la ruta de
una factura y devuelve un :class:`~ocr.bench.schema.EngineResult` con los campos extraídos, su
coste y su latencia. Las utilidades comunes (codificación de imagen, prompt de extracción y
parseo robusto del JSON del modelo) viven en :mod:`ocr.bench.engines.base` para que todos los
motores compartan exactamente el mismo contrato y se comparen de forma justa.
"""

from ocr.bench.engines.base import (
    EngineError,
    OcrEngine,
    build_extraction_messages,
    encode_image,
    parse_invoice_json,
)

__all__ = [
    "EngineError",
    "OcrEngine",
    "build_extraction_messages",
    "encode_image",
    "parse_invoice_json",
]
