"""Servicio de laboratorio PaddleOCR/PP-StructureV3 (R-041)."""

from ocr.layout_challengers import PaddleOCRLayoutEngine
from ocr.layout_service import create_layout_app

app = create_layout_app(PaddleOCRLayoutEngine())
