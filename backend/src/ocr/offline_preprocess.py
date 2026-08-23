"""Experimento offline de variantes de imagen contra un ground truth común (R-040)."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

import cv2
import numpy as np
from PIL import Image

from ocr.benchmark_scoring import score_combination
from ocr.preprocess._guards import open_bounded_image
from ocr.preprocess.clahe import clahe_invoice_image

__all__ = [
    "OFFLINE_VARIANTS",
    "OfflinePreprocessReport",
    "OfflineVariantRow",
    "build_offline_report",
    "build_offline_variants",
]

OFFLINE_VARIANTS = ("raw", "natural", "clahe", "gray", "sauvola")


@dataclass(frozen=True)
class OfflineVariantRow:
    variant: str
    content_sha256: str
    ground_truth_hash: str
    field_exact_accuracy: float | None
    aciertos: int
    comparables: int


@dataclass(frozen=True)
class OfflinePreprocessReport:
    ground_truth_hash: str
    rows: tuple[OfflineVariantRow, ...]


def build_offline_variants(content: bytes, content_type: str) -> dict[str, bytes]:
    """Genera todas las variantes desde `content`, sin persistencia ni llamadas externas."""
    original = open_bounded_image(content, content_type).convert("RGB")
    natural = _encode_png(original)
    gray = _encode_png(original.convert("L"))
    sauvola = _encode_png(_sauvola(original))
    return {
        "raw": content,
        "natural": natural,
        "clahe": clahe_invoice_image(content, content_type),
        "gray": gray,
        "sauvola": sauvola,
    }


def build_offline_report(
    readings: Mapping[str, Mapping[str, object]], truth: Mapping[str, object]
) -> OfflinePreprocessReport:
    """Puntúa lecturas ya disponibles; el mismo hash de verdad acompaña cada variante."""
    ground_truth_hash = _hash_json(truth)
    rows: list[OfflineVariantRow] = []
    for variant in OFFLINE_VARIANTS:
        reading = readings.get(variant, {})
        score = score_combination(reading, truth)
        comparable_accuracy = (
            score.aciertos / score.comparables if score.comparables else None
        )
        rows.append(
            OfflineVariantRow(
                variant=variant,
                content_sha256=str(reading.get("content_sha256", "")),
                ground_truth_hash=ground_truth_hash,
                field_exact_accuracy=comparable_accuracy,
                aciertos=score.aciertos,
                comparables=score.comparables,
            )
        )
    return OfflinePreprocessReport(ground_truth_hash=ground_truth_hash, rows=tuple(rows))


def _sauvola(image: Image.Image) -> Image.Image:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    mean = cv2.boxFilter(gray, cv2.CV_32F, (25, 25), normalize=True)
    squared_mean = cv2.boxFilter(gray * gray, cv2.CV_32F, (25, 25), normalize=True)
    standard_deviation = np.sqrt(np.maximum(squared_mean - mean * mean, 0))
    threshold = mean * (1 + 0.2 * (standard_deviation / 128 - 1))
    return Image.fromarray(np.where(gray > threshold, 255, 0).astype(np.uint8), mode="L")


def _encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _hash_json(value: Mapping[str, object]) -> str:
    import json

    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, default=_json_default).encode("utf-8")
    ).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Valor no serializable: {type(value).__name__}")
