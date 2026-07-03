"""Bench de evaluación de motores OCR (Fase 1, tarea 1.2)."""

from ocr.eval.ground_truth import load_ground_truth
from ocr.eval.models import GroundTruth, Party
from ocr.eval.scorer import (
    EngineAggregate,
    FieldResult,
    ReadingScore,
    aggregate_by_engine,
    score_reading,
)

__all__ = [
    "GroundTruth",
    "Party",
    "FieldResult",
    "ReadingScore",
    "EngineAggregate",
    "score_reading",
    "aggregate_by_engine",
    "load_ground_truth",
]
