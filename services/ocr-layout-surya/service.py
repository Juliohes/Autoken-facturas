"""Servicio de laboratorio Surya (R-042)."""

from ocr.layout_challengers import SuryaLayoutEngine
from ocr.layout_service import create_layout_app

app = create_layout_app(SuryaLayoutEngine())
