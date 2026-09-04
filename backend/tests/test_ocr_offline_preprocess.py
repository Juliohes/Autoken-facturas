"""Benchmark offline de preprocesado R-040."""

from __future__ import annotations

import io

from PIL import Image

from ocr.offline_preprocess import (
    OFFLINE_VARIANTS,
    build_offline_report,
    build_offline_variants,
)


def _image() -> bytes:
    image = Image.new("RGB", (80, 50), "white")
    for x in range(0, 80, 8):
        for y in range(50):
            image.putpixel((x, y), (60, 60, 60))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_r040_genera_las_cinco_variantes_desde_la_misma_imagen_original() -> None:
    variants = build_offline_variants(_image(), "image/jpeg")

    assert tuple(variants) == OFFLINE_VARIANTS
    assert all(variants[name] for name in OFFLINE_VARIANTS)
    assert len({hash(variants[name]) for name in OFFLINE_VARIANTS}) == 5


def test_r040_todas_las_variantes_comparten_ground_truth_y_reporte_no_llama_a_ia() -> None:
    truth = {"invoice_number": "F-1", "total_amount": "121.00"}
    readings = {
        name: {"invoice_number": "F-1", "total_amount": "121.00"} for name in OFFLINE_VARIANTS
    }

    report = build_offline_report(readings, truth)

    assert len(report.rows) == 5
    assert len({row.ground_truth_hash for row in report.rows}) == 1
    assert all(row.field_exact_accuracy == 1.0 for row in report.rows)
