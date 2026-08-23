"""Pruebas de contrato de telemetría R-047, sin datos de negocio ni infraestructura externa."""

from prometheus_client import Counter, Gauge, Histogram

from shared.metrics import (
    draft_save_failures,
    draft_save_latency_seconds,
    ocr_failure_rate,
    ocr_fallback_rate,
    ocr_fallback_seconds,
    ocr_processing_seconds,
    ocr_queue_wait_seconds,
    page_count_bucket,
    pending_count,
    ready_count,
    review_duration_seconds,
    upload_to_201_seconds,
)


def test_r047_agrupa_paginas_en_buckets_de_cardinalidad_acotada() -> None:
    assert [page_count_bucket(value) for value in (0, 1, 2, 5, 6, 10, 11, 100)] == [
        "1",
        "1",
        "2-5",
        "2-5",
        "6-10",
        "6-10",
        "11+",
        "11+",
    ]


def test_r047_metricas_no_tienen_tags_de_datos_fiscales() -> None:
    metrics = (
        upload_to_201_seconds,
        ocr_queue_wait_seconds,
        ocr_processing_seconds,
        ocr_fallback_seconds,
        ocr_fallback_rate,
        ocr_failure_rate,
        draft_save_latency_seconds,
        draft_save_failures,
        review_duration_seconds,
        pending_count,
        ready_count,
    )
    forbidden = {"cif", "proveedor", "invoice_number", "amount"}

    assert all(isinstance(metric, (Counter, Gauge, Histogram)) for metric in metrics)
    assert not forbidden.intersection(
        label
        for metric in metrics
        for label in metric._labelnames  # noqa: SLF001
    )
