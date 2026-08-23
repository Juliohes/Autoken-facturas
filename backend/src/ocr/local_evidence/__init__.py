"""Experimentos de evidencia OCR local, fuera del camino crítico."""

from ocr.local_evidence.tesseract_checker import (
    LocalTextEvidence,
    inspect_local_text,
    run_tesseract,
)

__all__ = ["LocalTextEvidence", "inspect_local_text", "run_tesseract"]
