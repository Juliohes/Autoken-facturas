"""Contrato de challengers de layout R-041/R-042."""

from __future__ import annotations

from ocr.layout import DocumentLayoutEngine, LayoutEvidence


class FakeLayoutEngine:
    name = "fake-layout"

    async def extract_layout(self, _pages) -> LayoutEvidence:
        return LayoutEvidence(
            engine=self.name,
            matched_features={"tax_lines": True, "tables": False},
            reading_order=["header", "tax_lines"],
        )


async def test_r041_un_challenger_cumple_el_contrato_sin_entrar_en_produccion() -> None:
    engine = FakeLayoutEngine()

    assert isinstance(engine, DocumentLayoutEngine)
    result = await engine.extract_layout([])

    assert result.engine == "fake-layout"
    assert result.matched_features["tax_lines"] is True
    assert result.reading_order == ["header", "tax_lines"]
