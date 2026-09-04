"""Adaptadores perezosos para challengers de layout de laboratorio (R-041/R-042).

Este módulo no importa PaddleOCR ni Surya. Los SDK solo se cargan dentro del proceso de laboratorio
que los solicita, de modo que el contenedor API principal no arrastra modelos ni dependencias GPU.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from importlib import import_module
from io import BytesIO
from typing import Any, Protocol, cast

import numpy as np
from PIL import Image, UnidentifiedImageError

from ocr.extraction import DocumentPage
from ocr.layout import LayoutEvidence

__all__ = ["PaddleOCRLayoutEngine", "SuryaLayoutEngine"]

_TAX_TERMS = re.compile(r"\b(?:iva|igic|vat|impuesto|tax)\b", re.IGNORECASE)
_TEXT_KEYS = ("rec_texts", "text_lines", "texts", "text", "content", "blocks", "lines")
_TABLE_KEYS = ("table", "tables", "table_res", "table_res_list")
_LAYOUT_KEYS = ("layout_res", "layout", "regions", "blocks")


class _PaddlePredictor(Protocol):
    def predict(self, *, input: object) -> Iterable[object]: ...


class _SuryaPredictor(Protocol):
    def predict(self, image: object) -> object: ...


class PaddleOCRLayoutEngine:
    """Challenger PaddleOCR/PP-StructureV3, ejecutado únicamente en el servicio lab."""

    name = "paddleocr-pp-structurev3"

    def __init__(self, predictor: _PaddlePredictor | None = None) -> None:
        self._predictor = predictor

    async def extract_layout(self, pages: Sequence[DocumentPage]) -> LayoutEvidence:
        predictor = self._predictor or self._create_predictor()
        self._predictor = predictor
        payloads: list[object] = []
        for page in pages:
            image = _decode_page(page)
            paddle_input = np.asarray(image) if isinstance(image, Image.Image) else image
            result = await asyncio.to_thread(predictor.predict, input=paddle_input)
            payloads.extend(_as_payloads(result))
        return _evidence(self.name, payloads)

    @staticmethod
    def _create_predictor() -> _PaddlePredictor:
        """Importa el SDK solo dentro del contenedor Paddle del perfil lab."""
        paddleocr = import_module("paddleocr")
        if os.getenv("PADDLE_PIPELINE", "structure").strip().lower() == "ocr":
            return cast(
                _PaddlePredictor,
                paddleocr.PaddleOCR(
                    text_detection_model_name=os.getenv(
                        "PADDLE_TEXT_DETECTION_MODEL", "PP-OCRv5_mobile_det"
                    ),
                    text_recognition_model_name=os.getenv(
                        "PADDLE_TEXT_RECOGNITION_MODEL", "latin_PP-OCRv5_mobile_rec"
                    ),
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                ),
            )
        pp_structure = getattr(paddleocr, "PPStructureV3", None)
        if pp_structure is not None:
            return cast(_PaddlePredictor, pp_structure(lang="es"))
        paddle_ocr = vars(paddleocr)["PaddleOCR"]
        return cast(_PaddlePredictor, paddle_ocr(lang="es"))


class SuryaLayoutEngine:
    """Challenger Surya, ejecutado únicamente en el servicio lab."""

    name = "surya"

    def __init__(self, predictor: _SuryaPredictor | None = None) -> None:
        self._predictor = predictor

    async def extract_layout(self, pages: Sequence[DocumentPage]) -> LayoutEvidence:
        predictor = self._predictor or self._create_predictor()
        self._predictor = predictor
        payloads: list[object] = []
        for page in pages:
            result = await asyncio.to_thread(predictor.predict, _decode_page(page))
            payloads.extend(_as_payloads(result))
        return _evidence(self.name, payloads)

    @staticmethod
    def _create_predictor() -> _SuryaPredictor:
        """Construye Surya bajo demanda para que el API nunca importe torch/Surya."""
        detection_module = import_module("surya.detection")
        recognition_module = import_module("surya.recognition")

        detection = vars(detection_module)["DetectionPredictor"]()
        recognition = vars(recognition_module)["RecognitionPredictor"]()

        class SuryaPredictor:
            def predict(self, image: object) -> object:
                detected = detection([image])[0]
                recognized = recognition([image])[0]
                return {
                    "regions": detected,
                    "text_lines": recognized,
                    "columns": _surya_column_count(detected),
                }

        return cast(_SuryaPredictor, SuryaPredictor())


def _decode_page(page: DocumentPage) -> object:
    """Entrega una imagen compatible al SDK y conserva bytes si el fichero no es imagen."""
    try:
        with Image.open(BytesIO(page.content)) as image:
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError):
        return page.content


def _as_payloads(value: object) -> list[object]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, (str, bytes, bytearray)):
        return [{"text": value.decode() if isinstance(value, bytes) else str(value)}]
    if isinstance(value, Iterable):
        return [_object_payload(item) for item in value]
    return [_object_payload(value)]


def _object_payload(value: object) -> object:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    raw_json = getattr(value, "json", None)
    if callable(raw_json):
        raw_json = raw_json()
    if isinstance(raw_json, Mapping):
        return raw_json
    if isinstance(raw_json, str):
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            return {"text": raw_json}
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if text is not None:
        return {"text": str(text)}
    return {"text": str(value)}


def _evidence(engine: str, payloads: Sequence[object]) -> LayoutEvidence:
    mappings = [payload for payload in payloads if isinstance(payload, Mapping)]
    text = _texts(mappings)
    has_layout = _has_key(mappings, _LAYOUT_KEYS)
    has_tables = _has_key(mappings, _TABLE_KEYS) or any(
        str(item.get("label", "")).lower() == "table"
        for mapping in mappings
        for item in _mapping_items(mapping, _LAYOUT_KEYS)
    )
    columns = any(_number_of_columns(mapping) > 1 for mapping in mappings)
    has_observation = bool(text or has_layout or has_tables or columns)
    return LayoutEvidence(
        engine=engine,
        matched_features={
            "tax_lines": any(_TAX_TERMS.search(item) for item in text) if has_observation else None,
            "tables": has_tables if has_observation else None,
            "multi_column": columns if has_observation else None,
            "label_value": _has_label_value(text) if has_observation else None,
        },
        reading_order=text,
    )


def _texts(mappings: Sequence[Mapping[str, Any]]) -> list[str]:
    values: list[str] = []
    for mapping in mappings:
        for key in _TEXT_KEYS:
            value = mapping.get(key)
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                values.extend(_text_item(item) for item in value if _text_item(item))
    return values


def _text_item(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        text = value.get("text") or value.get("content") or value.get("label") or value.get("html")
        return str(text) if text is not None else ""
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if text is not None:
        return str(text)
    return str(value)


def _has_key(mappings: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> bool:
    return any(any(key in mapping for key in keys) for mapping in mappings)


def _mapping_items(mapping: Mapping[str, Any], keys: Sequence[str]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, Mapping):
            result.append(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            result.extend(item for item in value if isinstance(item, Mapping))
    return result


def _number_of_columns(mapping: Mapping[str, Any]) -> int:
    value = mapping.get("columns") or mapping.get("column_count")
    return value if isinstance(value, int) else 0


def _surya_column_count(value: object) -> int:
    """Estima columnas a partir de los centros horizontales de las cajas detectadas."""
    payload = _object_payload(value)
    if not isinstance(payload, Mapping):
        return 0
    boxes = payload.get("bboxes")
    image_bbox = payload.get("image_bbox")
    if (
        not isinstance(boxes, Sequence)
        or not isinstance(image_bbox, Sequence)
        or len(image_bbox) < 3
    ):
        return 0
    centers: list[float] = []
    for box in boxes:
        if not isinstance(box, Mapping):
            continue
        polygon = box.get("polygon")
        if not isinstance(polygon, Sequence) or not polygon:
            continue
        x_values = [point[0] for point in polygon if isinstance(point, Sequence) and point]
        if x_values:
            centers.append(sum(x_values) / len(x_values))
    if len(centers) < 2:
        return 1 if centers else 0
    page_width = float(image_bbox[2]) - float(image_bbox[0])
    if page_width <= 0:
        return 1
    return 2 if max(centers) - min(centers) > page_width * 0.35 else 1


def _has_label_value(text: Sequence[str]) -> bool:
    return any(":" in item or "=" in item for item in text)
