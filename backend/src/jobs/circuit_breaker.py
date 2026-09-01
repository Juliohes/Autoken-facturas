"""Circuit breaker puro para proveedores OCR (R-045)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["CircuitBreaker", "CircuitState", "RedisCircuitBreaker"]


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Máquina de estados configurable, independiente del reloj y del almacenamiento Redis."""

    failure_threshold: int = 5
    failure_window_seconds: float = 60.0
    open_seconds: float = 30.0
    state: CircuitState = CircuitState.CLOSED
    _failure_times: list[float] = field(default_factory=list)
    _opened_at: float | None = None
    _probe_in_flight: bool = False

    def allow(self, now: float) -> bool:
        if self.state is CircuitState.OPEN:
            if self._opened_at is None or now - self._opened_at < self.open_seconds:
                return False
            self.state = CircuitState.HALF_OPEN
            self._probe_in_flight = False
        if self.state is CircuitState.HALF_OPEN:
            if self._probe_in_flight:
                return False
            self._probe_in_flight = True
        return True

    def record_failure(self, now: float) -> None:
        if self.state is CircuitState.HALF_OPEN:
            self._open(now)
            return
        self._failure_times = [
            failure
            for failure in self._failure_times
            if now - failure <= self.failure_window_seconds
        ]
        self._failure_times.append(now)
        if len(self._failure_times) >= self.failure_threshold:
            self._open(now)

    def record_success(self) -> None:
        self.state = CircuitState.CLOSED
        self._failure_times.clear()
        self._opened_at = None
        self._probe_in_flight = False

    def _open(self, now: float) -> None:
        self.state = CircuitState.OPEN
        self._opened_at = now
        self._probe_in_flight = False


class RedisCircuitBreaker:
    """Persistencia Redis de la máquina por `engine + model`.

    La política de fallback decide cuándo registrar el fallo; esta clase solo conserva estado y
    serializa el acceso para que un reinicio del worker no cierre el circuito accidentalmente.
    """

    def __init__(
        self,
        redis: Any,
        *,
        engine: str,
        model: str,
        failure_threshold: int = 5,
        failure_window_seconds: float = 60.0,
        open_seconds: float = 30.0,
        clock: Any = time.monotonic,
    ) -> None:
        self.redis = redis
        self.key = f"autoken:ocr:circuit:{engine}:{model}"
        self.probe_key = f"{self.key}:probe"
        self.failure_threshold = failure_threshold
        self.failure_window_seconds = failure_window_seconds
        self.open_seconds = open_seconds
        self.clock = clock

    async def allow(self) -> bool:
        breaker = await self._load()
        allowed = breaker.allow(self.clock())
        if not allowed:
            return False
        if breaker.state is CircuitState.HALF_OPEN:
            # SET NX makes the half-open probe exclusive across workers. The TTL lets a new
            # worker retry if the probe process dies before recording success/failure.
            claimed = await self.redis.set(
                self.probe_key,
                "1",
                nx=True,
                ex=max(int(self.open_seconds), 1),
            )
            if not claimed:
                return False
            await self._save(breaker)
        return allowed

    async def record_failure(self) -> None:
        breaker = await self._load()
        breaker.record_failure(self.clock())
        if breaker.state is CircuitState.OPEN:
            await self.redis.delete(self.probe_key)
        await self._save(breaker)

    async def record_success(self) -> None:
        breaker = await self._load()
        breaker.record_success()
        await self.redis.delete(self.probe_key)
        await self._save(breaker)

    async def _load(self) -> CircuitBreaker:
        raw = await self.redis.get(self.key)
        if raw is None:
            return CircuitBreaker(
                failure_threshold=self.failure_threshold,
                failure_window_seconds=self.failure_window_seconds,
                open_seconds=self.open_seconds,
            )
        data = json.loads(raw)
        return CircuitBreaker(
            failure_threshold=self.failure_threshold,
            failure_window_seconds=self.failure_window_seconds,
            open_seconds=self.open_seconds,
            state=CircuitState(data["state"]),
            _failure_times=data["failure_times"],
            _opened_at=data["opened_at"],
        )

    async def _save(self, breaker: CircuitBreaker) -> None:
        await self.redis.set(
            self.key,
            json.dumps(
                {
                    "state": breaker.state.value,
                    "failure_times": breaker._failure_times,
                    "opened_at": breaker._opened_at,
                }
            ),
            ex=max(int(self.failure_window_seconds + self.open_seconds), 60),
        )
