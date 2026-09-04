"""Pruebas de contrato de telemetría R-047, sin datos de negocio ni infraestructura externa."""

from prometheus_client import Counter, Gauge, Histogram

from shared.metrics import (
    db_session_setup_seconds,
    draft_save_failures,
    draft_save_latency_seconds,
    observe_db_session_setup,
    observe_upload_phase,
    ocr_failure_rate,
    ocr_fallback_rate,
    ocr_fallback_seconds,
    ocr_processing_seconds,
    ocr_queue_wait_seconds,
    page_count_bucket,
    pending_count,
    ready_count,
    review_duration_seconds,
    upload_phase_seconds,
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
        db_session_setup_seconds,
        ocr_queue_wait_seconds,
        ocr_processing_seconds,
        ocr_fallback_seconds,
        ocr_fallback_rate,
        ocr_failure_rate,
        draft_save_latency_seconds,
        draft_save_failures,
        review_duration_seconds,
        upload_phase_seconds,
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


def test_r050_registra_tiempo_por_fase_de_subida_sin_datos_de_negocio() -> None:
    child = upload_phase_seconds.labels(phase="validation")
    before = next(
        sample.value
        for sample in child._child_samples()
        if sample.name == "_count"  # noqa: SLF001
    )

    with observe_upload_phase("validation"):
        pass

    after = next(
        sample.value
        for sample in child._child_samples()
        if sample.name == "_count"  # noqa: SLF001
    )
    assert after == before + 1
    assert "tenant" not in upload_phase_seconds._labelnames  # noqa: SLF001


def test_r050_rechaza_fases_no_controladas_para_evitar_cardinalidad_infinita() -> None:
    try:
        with observe_upload_phase("tenant-id"):
            pass
    except ValueError as exc:
        assert str(exc) == "Unknown upload phase: tenant-id"
    else:
        raise AssertionError("An unknown upload phase must be rejected")


def test_r050_mide_la_preparacion_de_sesiones_rls_sin_etiquetas_de_negocio() -> None:
    child = db_session_setup_seconds.labels(phase="validation")
    before = next(
        sample.value for sample in child._child_samples() if sample.name == "_count"  # noqa: SLF001
    )

    with observe_upload_phase("validation"), observe_db_session_setup():
        pass

    after = next(
        sample.value for sample in child._child_samples() if sample.name == "_count"  # noqa: SLF001
    )
    assert after == before + 1
    assert db_session_setup_seconds._labelnames == ("phase",)  # noqa: SLF001
