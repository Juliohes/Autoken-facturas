"""Constantes de dominio del intake de ficheros (S2.1/S2.3).

Fuente ÚNICA de la máquina de estados de `uploaded_files.status`: la comparten el intake (que crea
el fichero en `pending_ocr`) y el worker OCR (que lo transiciona a `ocr_done`/`needs_review`/
`ocr_failed`). El worker importa estos valores en vez de repetir literales sueltos: un estado nuevo
se añade aquí y en ningún otro sitio.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["FileStatus", "ProcessingStage"]


class FileStatus(StrEnum):
    """Estados del ciclo de vida de un fichero de intake (`uploaded_files.status`).

    `pending_ocr` (recién subido, S2.1) -> `ocr_done` (OCR con todo alto y válido) / `needs_review`
    (algo dudoso/no leído/validación KO) / `ocr_failed` (el motor falló) / `capture_unreadable`
    (S6.14: el motor respondió pero la imagen en sí es el problema — repetir la foto, no abrir un
    formulario de revisión con campos vacíos). El worker (S2.3/S6.14) es quien hace la transición
    desde `pending_ocr`. Al confirmar (S2.5), un fichero en `ocr_done`/`needs_review` pasa a
    `confirmed` (ya tiene factura persistida); `capture_unreadable` NUNCA es confirmable (no entra
    en `invoicing.service._CONFIRMABLE_STATES`), igual que `ocr_failed`.
    """

    PENDING_OCR = "pending_ocr"
    PROCESSING = "processing"
    OCR_DONE = "ocr_done"
    NEEDS_REVIEW = "needs_review"
    OCR_FAILED = "ocr_failed"
    CAPTURE_UNREADABLE = "capture_unreadable"
    CONFIRMED = "confirmed"


class ProcessingStage(StrEnum):
    """Etapas transitorias del OCR, separadas del estado final del fichero (R-016)."""

    QUEUED = "queued"
    LOADING_DOCUMENT = "loading_document"
    PRIMARY_OCR = "primary_ocr"
    VALIDATING = "validating"
    FALLBACK_OCR = "fallback_ocr"
    CONSENSUS = "consensus"
    PERSISTING = "persisting"
