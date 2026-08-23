"""Máquina de estados del circuit breaker R-045."""

from jobs.circuit_breaker import CircuitBreaker, CircuitState


def test_r045_abre_tras_cinco_fallos_y_no_deja_crecer_el_fallback() -> None:
    breaker = CircuitBreaker(failure_threshold=5, failure_window_seconds=60, open_seconds=30)

    for _ in range(4):
        assert breaker.allow(0.0) is True
        breaker.record_failure(0.0)
    assert breaker.allow(0.0) is True
    breaker.record_failure(0.0)

    assert breaker.state == CircuitState.OPEN
    assert breaker.allow(1.0) is False


def test_r045_pasa_a_half_open_y_cierra_con_un_probe_exitoso() -> None:
    breaker = CircuitBreaker(failure_threshold=1, failure_window_seconds=60, open_seconds=30)
    breaker.record_failure(0.0)

    assert breaker.allow(29.9) is False
    assert breaker.allow(30.0) is True
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.allow(30.0) is False

    breaker.record_success()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow(30.0) is True
