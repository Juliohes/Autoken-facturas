"""Configuración de logging estructurado con structlog (JSON + correlation id).

El correlation id se guarda en contextvars y se inyecta automáticamente en
cada log gracias a `merge_contextvars`, de modo que todos los logs de una
misma petición comparten identificador de correlación.
"""

import logging
import sys
from typing import cast

import structlog

from shared.config import LogLevel


def configure_logging(log_level: LogLevel = LogLevel.INFO) -> None:
    """Configura structlog para emitir logs JSON con correlation id.

    El nivel ya viene validado por `Settings` (conjunto cerrado `LogLevel`), así que se
    resuelve sin valor de reserva silencioso: un nivel inesperado falla en vez de caer a
    INFO sin avisar (BP-5).
    """
    level = getattr(logging, log_level.upper())

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Devuelve un logger estructurado."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
