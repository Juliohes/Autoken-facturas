"""Extractor OCR determinista para la carga sintética R-050.

Este módulo solo se activa cuando `APP_ENV=load_test`. No conoce credenciales ni hace llamadas de
red; permite medir intake, cola, persistencia, polling y aislamiento sin consumir un proveedor real.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ocr.extraction import (
    DocumentPage,
    ExtractedInvoice,
    ExtractedTaxId,
    ExtractedTaxLine,
)

__all__ = ["LoadTestInvoiceExtractor"]


class LoadTestInvoiceExtractor:
    """Devuelve siempre una factura sintética válida, sin leer el contenido recibido."""

    async def extract(self, content: bytes, content_type: str) -> ExtractedInvoice:  # noqa: ARG002
        return self._invoice()

    async def extract_pages(self, pages: list[DocumentPage]) -> ExtractedInvoice:  # noqa: ARG002
        return self._invoice()

    @staticmethod
    def _invoice() -> ExtractedInvoice:
        return ExtractedInvoice(
            issue_date=date(2026, 1, 1),
            issue_date_confidence="alta",
            total_amount=Decimal("121.00"),
            total_confidence="alta",
            net_amount=Decimal("100.00"),
            net_amount_confidence="alta",
            tax_amount=Decimal("21.00"),
            tax_amount_confidence="alta",
            irpf_rate=None,
            irpf_rate_confidence="alta",
            irpf_amount=None,
            irpf_amount_confidence="alta",
            invoice_number="R050-SYNTHETIC",
            invoice_number_confidence="alta",
            tax_lines=(
                ExtractedTaxLine(
                    base=Decimal("100.00"), rate=Decimal("21"), cuota=Decimal("21.00")
                ),
            ),
            tax_ids=(
                ExtractedTaxId(
                    value="B06339923",
                    name="Proveedor sintético R050",
                    value_confidence="alta",
                    name_confidence="alta",
                ),
            ),
            engine="load-test",
            model="deterministic",
            raw={"load_test": True},
        )
