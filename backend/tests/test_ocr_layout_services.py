"""Comportamiento de los challengers de layout R-041/R-042."""

from __future__ import annotations

import base64
from io import BytesIO
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from PIL import Image

from ocr.extraction import DocumentPage
from ocr.layout import DocumentLayoutEngine, LayoutEvidence
from ocr.layout_challengers import PaddleOCRLayoutEngine, SuryaLayoutEngine
from ocr.layout_service import create_layout_app


class FakePaddlePredictor:
    def predict(self, *, input: object) -> list[dict[str, object]]:
        assert input is not None
        return [
            {
                "rec_texts": ["IVA 21%", "Base imponible"],
                "layout_res": [{"label": "table"}],
                "columns": 2,
            }
        ]


class FakeSuryaPredictor:
    def predict(self, image: object) -> dict[str, object]:
        assert image is not None
        return {
            "text_lines": [{"text": "IVA 21%"}, {"text": "Total"}],
            "tables": [{"bbox": [0, 0, 10, 10]}],
            "columns": 2,
        }


class JsonResult:
    json = {"rec_texts": ["IVA 21%"], "columns": 2}


class FakePaddleJsonPredictor:
    def predict(self, *, input: object) -> list[JsonResult]:
        assert input is not None
        return [JsonResult()]


class FakePaddleArrayPredictor:
    def predict(self, *, input: object) -> list[dict[str, object]]:
        assert isinstance(input, np.ndarray)
        return [{"rec_texts": ["IVA 21%"]}]


@pytest.mark.parametrize(
    ("engine_type", "predictor", "expected_engine"),
    [
        (PaddleOCRLayoutEngine, FakePaddlePredictor(), "paddleocr-pp-structurev3"),
        (SuryaLayoutEngine, FakeSuryaPredictor(), "surya"),
    ],
)
async def test_layout_challenger_extrae_features_comparables(
    engine_type: type[DocumentLayoutEngine],
    predictor: object,
    expected_engine: str,
) -> None:
    engine = engine_type(predictor)

    assert isinstance(engine, DocumentLayoutEngine)
    result = await engine.extract_layout(
        [DocumentPage(b"not-an-image", "application/octet-stream")]
    )

    assert result.engine == expected_engine
    assert result.matched_features["tax_lines"] is True
    assert result.matched_features["tables"] is True
    assert result.matched_features["multi_column"] is True
    assert result.reading_order


async def test_layout_service_recibe_paginas_y_devuelve_evidencia() -> None:
    class FakeEngine:
        name = "fake-layout"

        async def extract_layout(self, pages: list[DocumentPage]) -> LayoutEvidence:
            assert pages[0].content == b"invoice"
            assert pages[0].content_type == "image/png"
            return LayoutEvidence(engine=self.name, matched_features={"tables": False})

    app = create_layout_app(FakeEngine())
    encoded = base64.b64encode(b"invoice").decode("ascii")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://layout") as client:
        response = await client.post(
            "/layout",
            json={"pages": [{"content_base64": encoded, "content_type": "image/png"}]},
        )

    assert response.status_code == 200
    assert response.json() == {
        "engine": "fake-layout",
        "matched_features": {"tables": False},
        "reading_order": [],
    }


async def test_layout_challenger_admite_resultado_sdk_con_json_mapping() -> None:
    result = await PaddleOCRLayoutEngine(FakePaddleJsonPredictor()).extract_layout(
        [DocumentPage(b"not-an-image", "application/octet-stream")]
    )

    assert result.matched_features["tax_lines"] is True
    assert result.matched_features["multi_column"] is True


async def test_paddle_recibe_imagen_como_array_compatible_con_pp_structure() -> None:
    image = Image.new("RGB", (2, 2), color="white")
    content = BytesIO()
    image.save(content, format="PNG")

    result = await PaddleOCRLayoutEngine(FakePaddleArrayPredictor()).extract_layout(
        [DocumentPage(content.getvalue(), "image/png")]
    )

    assert result.matched_features["tax_lines"] is True


def test_paddle_puede_construir_modo_ocr_ligero(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakePaddleOCR:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setenv("PADDLE_PIPELINE", "ocr")
    monkeypatch.setattr(
        "ocr.layout_challengers.import_module",
        lambda name: SimpleNamespace(PaddleOCR=FakePaddleOCR),
    )

    PaddleOCRLayoutEngine._create_predictor()

    assert captured == {
        "text_detection_model_name": "PP-OCRv5_mobile_det",
        "text_recognition_model_name": "latin_PP-OCRv5_mobile_rec",
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }
