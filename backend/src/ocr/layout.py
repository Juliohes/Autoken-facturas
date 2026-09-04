"""Contrato mínimo para challengers de layout solo de laboratorio (R-041/R-042)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ocr.extraction import DocumentPage

__all__ = ["DocumentLayoutEngine", "LayoutEvidence"]


class LayoutEvidence(BaseModel):
    """Resultado comparable de layout, no una extracción fiscal de producción."""

    engine: str
    matched_features: dict[str, bool | None] = Field(default_factory=dict)
    reading_order: list[str] = Field(default_factory=list)


@runtime_checkable
class DocumentLayoutEngine(Protocol):
    """Interfaz que implementarán PaddleOCR/Surya en servicios de laboratorio separados."""

    name: str

    async def extract_layout(self, pages: Sequence[DocumentPage]) -> LayoutEvidence:
        """Analiza layout sin decidir valores fiscales ni alterar el OCR principal."""
