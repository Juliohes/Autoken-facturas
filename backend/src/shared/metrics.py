"""Métrica HTTP transversal (S5.6): contador de peticiones por método+código de estado, usado por
`shared.middleware.MetricsMiddleware`.

El endpoint que expone esto en formato Prometheus (`GET /metrics`) vive en `jobs.metrics_router`,
no aquí: ese endpoint también agrega la salud de la cola OCR (`jobs.monitoring`), y `shared` no debe
depender de un contexto de dominio concreto como `jobs` (auditoría de arquitectura S5.6 — antes
`shared/metrics.py` importaba `jobs.monitoring`, invirtiendo la dirección de dependencias
esperada). Este módulo solo contiene la primitiva realmente transversal.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

from prometheus_client import Counter, Gauge, Histogram

# Métodos HTTP que la app realmente enruta. Cualquier otro token se agrupa en "OTHER": el método
# de la petición NO es un conjunto acotado a nivel de servidor ASGI (un cliente puede mandar
# cualquier token), así que usarlo tal cual como label crearía una serie de Prometheus nueva por
# cada valor distinto que un atacante no autenticado quisiera mandar — cardinalidad sin límite,
# consumida en la memoria del propio proceso de la API (auditoría de seguridad, hallazgo alto).
_KNOWN_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})

http_requests_total = Counter(
    "autoken_http_requests_total",
    "Peticiones HTTP totales, por método y código de estado (deriva la tasa de 5xx)",
    ["method", "status"],
)

upload_to_201_seconds = Histogram(
    "autoken_upload_to_201_seconds",
    "Tiempo de respuesta de una subida aceptada con HTTP 201",
)
upload_phase_seconds = Histogram(
    "autoken_upload_phase_seconds",
    "Tiempo de cada fase técnica de una subida, sin datos de negocio",
    ["phase"],
)
db_session_setup_seconds = Histogram(
    "autoken_db_session_setup_seconds",
    "Tiempo para adquirir una sesión y fijar el contexto RLS",
    ["phase"],
)

_current_upload_phase: ContextVar[str | None] = ContextVar("current_upload_phase", default=None)
_UPLOAD_PHASES = frozenset(
    {
        "authorization",
        "identity",
        "rate_limit",
        "request_body",
        "validation",
        "deduplication",
        "antivirus",
        "storage",
        "persistence",
    }
)


@contextmanager
def observe_upload_phase(phase: str) -> Iterator[None]:
    """Mide una fase conocida de intake sin permitir etiquetas arbitrarias."""
    if phase not in _UPLOAD_PHASES:
        raise ValueError(f"Unknown upload phase: {phase}")
    token = _current_upload_phase.set(phase)
    started = perf_counter()
    try:
        yield
    finally:
        upload_phase_seconds.labels(phase=phase).observe(perf_counter() - started)
        _current_upload_phase.reset(token)


@contextmanager
def observe_db_session_setup() -> Iterator[None]:
    """Mide la adquisición de conexión y la configuración RLS de una sesión."""
    started = perf_counter()
    try:
        yield
    finally:
        db_session_setup_seconds.labels(phase=_current_upload_phase.get() or "other").observe(
            perf_counter() - started
        )


ocr_queue_wait_seconds = Histogram(
    "autoken_ocr_queue_wait_seconds",
    "Tiempo que un documento espera antes de comenzar OCR",
    ["engine", "model", "page_count_bucket"],
)
ocr_processing_seconds = Histogram(
    "autoken_ocr_processing_seconds",
    "Tiempo de procesamiento OCR",
    ["engine", "model", "status", "page_count_bucket"],
)
ocr_fallback_seconds = Histogram(
    "autoken_ocr_fallback_seconds",
    "Tiempo de la lectura OCR de fallback",
    ["engine", "model"],
)
ocr_fallback_total = Counter(
    "autoken_ocr_fallback_total",
    "Lecturas OCR de fallback iniciadas",
    ["engine", "model"],
)
ocr_fallback_rate = Gauge(
    "autoken_ocr_fallback_rate",
    "Proporción acumulada de OCR que necesitó fallback",
    ["engine", "model"],
)
ocr_completed_total = Counter(
    "autoken_ocr_completed_total",
    "OCR terminados por estado",
    ["engine", "model", "status"],
)
ocr_failure_rate = Gauge(
    "autoken_ocr_failure_rate",
    "Proporción acumulada de OCR fallidos",
    ["engine", "model"],
)
ocr_provider_429_total = Counter(
    "autoken_ocr_provider_429_total",
    "Respuestas 429 de proveedores OCR, sin datos de factura",
    ["engine", "model"],
)
draft_save_latency_seconds = Histogram(
    "autoken_draft_save_latency_seconds",
    "Tiempo de persistencia de un borrador",
)
draft_save_failures = Counter(
    "autoken_draft_save_failures_total",
    "Fallos al persistir borradores",
)
review_duration_seconds = Histogram(
    "autoken_review_duration_seconds",
    "Tiempo desde el fin del OCR hasta el comienzo de la confirmación",
)
pending_count = Gauge("autoken_pending_count", "Documentos pendientes de OCR")
ready_count = Gauge("autoken_ready_count", "Documentos listos para revisión o confirmación")

_ocr_completion_counts: dict[tuple[str, str], int] = {}
_ocr_failure_counts: dict[tuple[str, str], int] = {}
_ocr_fallback_counts: dict[tuple[str, str], int] = {}


def page_count_bucket(page_count: int) -> str:
    """Agrupa el número de páginas para mantener la cardinalidad de Prometheus acotada."""
    if page_count <= 1:
        return "1"
    if page_count <= 5:
        return "2-5"
    if page_count <= 10:
        return "6-10"
    return "11+"


def record_ocr_completion(*, engine: str, model: str, status: str) -> None:
    """Actualiza los contadores y tasas globales sin añadir dimensiones de negocio."""
    ocr_completed_total.labels(engine=engine, model=model, status=status).inc()
    key = (engine, model)
    _ocr_completion_counts[key] = _ocr_completion_counts.get(key, 0) + 1
    if status == "failed":
        _ocr_failure_counts[key] = _ocr_failure_counts.get(key, 0) + 1
    completed = _ocr_completion_counts[key]
    failed = _ocr_failure_counts.get(key, 0)
    ocr_failure_rate.labels(engine=engine, model=model).set(failed / completed if completed else 0)
    fallback = _ocr_fallback_counts.get(key, 0)
    ocr_fallback_rate.labels(engine=engine, model=model).set(
        fallback / completed if completed else 0
    )


def record_ocr_fallback(*, engine: str, model: str) -> None:
    """Registra una lectura fallback y actualiza su tasa visible."""
    key = (engine, model)
    _ocr_fallback_counts[key] = _ocr_fallback_counts.get(key, 0) + 1
    ocr_fallback_total.labels(engine=engine, model=model).inc()
    completed = _ocr_completion_counts.get(key, 0)
    ocr_fallback_rate.labels(engine=engine, model=model).set(
        _ocr_fallback_counts[key] / completed if completed else 0
    )


def is_provider_rate_limited(error: BaseException) -> bool:
    """Detecta un 429 normalizado por un adaptador sin registrar el mensaje del proveedor."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for attribute in ("status_code", "status", "code"):
            value = getattr(current, attribute, None)
            if value == 429 or value == "429":
                return True
        normalized = str(current).lower()
        if (
            "429" in normalized
            or "resource_exhausted" in normalized
            or "too many requests" in normalized
        ):
            return True
        current = current.__cause__
    return False


def record_provider_rate_limit(*, engine: str, model: str) -> None:
    """Cuenta un 429 del proveedor con etiquetas técnicas acotadas."""
    ocr_provider_429_total.labels(engine=engine, model=model).inc()


def normalize_http_method(method: str) -> str:
    """Método conocido tal cual, o `"OTHER"` si no lo es (cardinalidad acotada, ver arriba)."""
    return method if method in _KNOWN_HTTP_METHODS else "OTHER"
