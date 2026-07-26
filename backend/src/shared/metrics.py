"""Métrica HTTP transversal (S5.6): contador de peticiones por método+código de estado, usado por
`shared.middleware.MetricsMiddleware`.

El endpoint que expone esto en formato Prometheus (`GET /metrics`) vive en `jobs.metrics_router`,
no aquí: ese endpoint también agrega la salud de la cola OCR (`jobs.monitoring`), y `shared` no debe
depender de un contexto de dominio concreto como `jobs` (auditoría de arquitectura S5.6 — antes
`shared/metrics.py` importaba `jobs.monitoring`, invirtiendo la dirección de dependencias
esperada). Este módulo solo contiene la primitiva realmente transversal.
"""

from __future__ import annotations

from prometheus_client import Counter

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


def normalize_http_method(method: str) -> str:
    """Método conocido tal cual, o `"OTHER"` si no lo es (cardinalidad acotada, ver arriba)."""
    return method if method in _KNOWN_HTTP_METHODS else "OTHER"
