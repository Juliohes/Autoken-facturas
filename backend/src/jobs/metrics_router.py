"""Endpoint `GET /metrics` (S5.6): agrega el contador HTTP transversal (`shared.metrics`) con la
salud de la cola OCR (`jobs.monitoring`) en un único texto Prometheus.

Vive en `jobs`, no en `shared`, a propósito (auditoría de arquitectura S5.6): `shared` es la capa
fundacional de la que dependen los contextos de dominio, nunca al revés; este endpoint SÍ conoce un
detalle de dominio concreto (la cola OCR de arq), así que el punto de composición que junta ambas
fuentes vive en `jobs`, que ya depende de `shared` (no genera dependencia circular).

`GET /metrics` es público (sin autenticación de aplicación, spec §4): es el criterio estándar del
ecosistema Prometheus, protegido a nivel de red en producción (solo el Prometheus interno lo
alcanza), nunca expone datos de negocio de un tenant (solo agregados operativos transversales).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Gauge, generate_latest

from jobs.monitoring import ocr_queue_health
from shared.config import Settings, get_settings

router = APIRouter(tags=["observability"])

ocr_queue_depth = Gauge(
    "autoken_ocr_queue_depth",
    "Trabajos OCR pendientes (aún no empezados) en la cola de arq",
)

_OLDEST_PENDING_METRIC = b"autoken_ocr_queue_oldest_pending_seconds"


def _render_oldest_pending_line(age_seconds: float) -> bytes:
    """Bloque de texto Prometheus (HELP+TYPE+valor) para la antigüedad del más viejo pendiente.

    Se ensambla a mano, en vez de con un `Gauge` normal, para que la métrica desaparezca de verdad
    cuando la cola está vacía (spec C6): un `Gauge` conservaría el último valor visto para siempre
    aunque la cola se vaciara, leyéndose como "el más viejo lleva X segundos" cuando en realidad no
    hay ninguno. NO convertir esto a un `Gauge.set()` normal sin releer C6 primero.
    """
    return (
        b"# HELP "
        + _OLDEST_PENDING_METRIC
        + b" Antiguedad en segundos del trabajo OCR pendiente mas viejo.\n"
        + b"# TYPE "
        + _OLDEST_PENDING_METRIC
        + b" gauge\n"
        + _OLDEST_PENDING_METRIC
        + f" {age_seconds}\n".encode()
    )


@router.get("/metrics")
async def metrics(settings: Annotated[Settings, Depends(get_settings)]) -> Response:
    """Peticiones HTTP + salud de la cola OCR, en formato de texto Prometheus."""
    health = await ocr_queue_health(settings)
    if health is not None:
        ocr_queue_depth.set(health.depth)

    body = generate_latest(REGISTRY)
    if health is not None and health.oldest_pending_age_seconds is not None:
        body += _render_oldest_pending_line(health.oldest_pending_age_seconds)
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)
