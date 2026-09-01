"""Máquina de estados del circuit breaker R-045."""

from jobs.circuit_breaker import CircuitBreaker, CircuitState


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int, nx: bool = False) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


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


async def test_r045_persisted_probe_is_unico_entre_workers() -> None:
    from jobs.circuit_breaker import RedisCircuitBreaker

    redis = FakeRedis()
    now = 0.0
    first = RedisCircuitBreaker(
        redis,
        engine="gemini",
        model="flash",
        failure_threshold=1,
        open_seconds=30,
        clock=lambda: now,
    )
    second = RedisCircuitBreaker(
        redis,
        engine="gemini",
        model="flash",
        failure_threshold=1,
        open_seconds=30,
        clock=lambda: now,
    )

    await first.record_failure()
    now = 30.0

    assert await first.allow() is True
    assert await second.allow() is False
