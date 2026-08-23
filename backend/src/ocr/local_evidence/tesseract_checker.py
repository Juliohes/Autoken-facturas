"""Comprobación opcional con Tesseract (R-039), nunca fuente de verdad."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from time import perf_counter

from pydantic import BaseModel

__all__ = ["LocalTextEvidence", "inspect_local_text", "run_tesseract"]


class LocalTextEvidence(BaseModel):
    available: bool
    matched_fields: dict[str, bool | None]
    duration_ms: int


def inspect_local_text(
    text: str | None, expected_fields: Mapping[str, str | None]
) -> LocalTextEvidence:
    """Compara texto OCR local con valores ya leídos sin invalidar la factura si faltan."""
    started = perf_counter()
    if text is None:
        return LocalTextEvidence(
            available=False,
            matched_fields=dict.fromkeys(expected_fields, None),
            duration_ms=_duration_ms(started),
        )
    normalized_text = _normalize_text(text)
    return LocalTextEvidence(
        available=True,
        matched_fields={
            field: _contains_value(normalized_text, value) if value is not None else None
            for field, value in expected_fields.items()
        },
        duration_ms=_duration_ms(started),
    )


def run_tesseract(
    image: bytes, expected_fields: Mapping[str, str | None], *, timeout_seconds: float = 5.0
) -> LocalTextEvidence:
    """Ejecuta Tesseract solo si está instalado; el timeout no bloquea el OCR principal."""
    if shutil.which("tesseract") is None:
        return inspect_local_text(None, expected_fields)
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout"],
            input=image,
            capture_output=True,
            check=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return inspect_local_text(None, expected_fields)
    return inspect_local_text(result.stdout.decode("utf-8", errors="replace"), expected_fields)


def _contains_value(text: str, value: str) -> bool:
    normalized_value = _normalize_text(value)
    if not normalized_value:
        return False
    if _looks_numeric(value):
        expected = _parse_amount(value)
        if expected is not None:
            return any(_parse_amount(token) == expected for token in _amount_tokens(text))
    if normalized_value in text:
        return True
    compact_value = re.sub(r"[\s.\-]", "", normalized_value)
    compact_text = re.sub(r"[\s.\-]", "", text)
    return len(compact_value) >= 8 and compact_value in compact_text


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _looks_numeric(value: str) -> bool:
    return bool(re.fullmatch(r"\s*[-+]?\d+(?:[.,]\d+)?\s*", value))


def _parse_amount(value: str) -> Decimal | None:
    try:
        return Decimal(value.strip().replace(",", "."))
    except InvalidOperation:
        return None


def _amount_tokens(text: str) -> list[str]:
    return re.findall(r"[-+]?\d+(?:[.,]\d+)?", text)


def _duration_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
