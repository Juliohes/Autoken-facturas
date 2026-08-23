"""Pruebas de comportamiento del cálculo ETA R-048."""

from ocr.eta import estimate_eta


def test_no_muestra_eta_antes_de_treinta_finalizaciones() -> None:
    assert estimate_eta(
        pending_ahead=2,
        effective_concurrency=4,
        processing_seconds=[10.0] * 29,
        queue_wait_seconds=[2.0] * 29,
    ) is None


def test_calcula_rango_concurrente_y_no_multiplica_por_slots() -> None:
    eta = estimate_eta(
        pending_ahead=5,
        effective_concurrency=4,
        processing_seconds=[20.0] * 30,
        queue_wait_seconds=[5.0] * 30,
    )

    assert eta is not None
    assert eta.minimum_seconds == 45
    assert eta.maximum_seconds == 55


def test_eta_no_devuelve_valores_con_concurrencia_invalida() -> None:
    assert estimate_eta(
        pending_ahead=1,
        effective_concurrency=0,
        processing_seconds=[10.0] * 30,
        queue_wait_seconds=[2.0] * 30,
    ) is None
