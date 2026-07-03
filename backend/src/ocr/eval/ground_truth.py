"""Carga de los ficheros de ground truth del bench OCR (1.2)."""

from __future__ import annotations

from pathlib import Path

from ocr.eval.models import GroundTruth


def load_ground_truth(directory: str | Path) -> tuple[GroundTruth, ...]:
    """Carga todos los `*.json` de un directorio como `GroundTruth`, ordenados por nombre."""
    files = sorted(Path(directory).glob("*.json"))
    return tuple(GroundTruth.model_validate_json(f.read_text("utf-8")) for f in files)
