"""Cálculo puro de ETA para OCR (R-048)."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from statistics import quantiles

MINIMUM_SAMPLES = 30


@dataclass(frozen=True)
class EtaRange:
    minimum_seconds: int
    maximum_seconds: int


def _percentile(values: list[float], percentile: int) -> float:
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[percentile - 1]


def estimate_eta(
    *,
    pending_ahead: int,
    effective_concurrency: int,
    processing_seconds: list[float],
    queue_wait_seconds: list[float],
) -> EtaRange | None:
    """Devuelve un rango conservador o ``None`` si aún no hay base estadística suficiente."""
    if len(processing_seconds) < MINIMUM_SAMPLES:
        return None
    if not processing_seconds or not queue_wait_seconds or effective_concurrency < 1:
        return None

    waves = ceil(max(pending_ahead, 0) / effective_concurrency)
    processing_p75 = _percentile(processing_seconds, 75)
    queue_p50 = _percentile(queue_wait_seconds, 50)
    queue_p75 = _percentile(queue_wait_seconds, 75)
    lower = queue_p50 + waves * processing_p75
    upper = queue_p75 + waves * processing_p75 * 1.25
    return EtaRange(
        minimum_seconds=max(1, int(lower // 5 * 5)),
        maximum_seconds=max(5, int(ceil(upper / 5) * 5)),
    )
