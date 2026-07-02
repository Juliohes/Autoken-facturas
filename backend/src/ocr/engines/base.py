"""Interfaz común de los motores de lectura OCR (capa de bench, Fase 1).

Todos los candidatos del bench (Mistral OCR 4, Azure DocIntel, PaddleOCR, Qwen...) implementan
`OcrEngine` y devuelven el mismo `OcrResult` normalizado. Así el orquestador del bench puede
compararlos, enrutar por confianza y, en el futuro, hacer fallback de uno a otro. El ganador
formal del motor de producción lo decide el bench (ADR-0007), no esta capa.
"""

from __future__ import annotations

import abc
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["OcrEngine", "OcrResult", "OcrPage", "OcrError"]


class OcrError(Exception):
    """Error base de la capa de motores OCR. Cada motor concreto define su subclase."""


@dataclass(frozen=True)
class OcrPage:
    """Una página del documento tras el OCR: texto en markdown + dimensiones.

    El detalle fino del proveedor (bloques, bounding boxes, confidencias) se conserva en
    `OcrResult.raw`; aquí solo se normaliza lo común a todos los motores.
    """

    index: int
    markdown: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class OcrResult:
    """Resultado normalizado de un motor OCR, independiente del proveedor.

    `raw` conserva la respuesta completa del proveedor (nada se pierde) para que el scorer del
    bench pueda explotar bloques/bounding boxes/confidencias sin acoplarse a esta capa.
    """

    engine: str
    model: str
    pages: tuple[OcrPage, ...]
    usage: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Texto completo: el markdown de todas las páginas unido."""
        return "\n\n".join(page.markdown for page in self.pages)


class OcrEngine(abc.ABC):
    """Motor de lectura OCR. Contrato común para todos los candidatos del bench."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Identificador corto y estable del motor (p. ej. `mistral-ocr-4`)."""

    @abc.abstractmethod
    async def extract(self, file_path: str | Path) -> OcrResult:
        """Extrae el contenido de un documento y lo devuelve normalizado.

        Debe lanzar una subclase de `OcrError` ante cualquier fallo (fichero inexistente,
        credenciales, timeout, error del proveedor); nunca una excepción cruda del SDK.
        """

    async def batch_extract(self, file_paths: Sequence[str | Path]) -> list[OcrResult]:
        """Procesa varios documentos en paralelo (concurrencia local con `asyncio.gather`).

        NO es un endpoint batch del proveedor: es conveniencia sobre `extract`. Si un motor
        tiene batch nativo más eficiente, lo sobreescribe.
        """
        return list(await asyncio.gather(*(self.extract(path) for path in file_paths)))
