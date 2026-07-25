"""Comparativa original-vs-realzada de una lectura OCR (S2.10).

Módulo PURO (sin I/O): reutiliza `ocr.analysis.analyze_invoice`, la MISMA regla de negocio que ya
decide `auto_ok`/`needs_review` en producción (S2.3), para puntuar cada lectura con señales
deterministas — nunca con una opinión subjetiva de una IA sobre "cuál es mejor". Ganar es tener más
señales objetivas a favor; un empate exacto da `tie`, nunca un ganador inventado (anti-alucinación
del veredicto, spec C10).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ocr.analysis import InvoiceAnalysis, analyze_invoice
from ocr.extraction import ExtractedInvoice
from ocr.scoring import score_analysis

__all__ = ["Winner", "ComparisonVerdict", "compare_readings"]

Winner = Literal["original", "enhanced", "tie"]


@dataclass(frozen=True)
class ComparisonVerdict:
    """Veredicto de comparar la lectura de una imagen original contra su versión realzada."""

    original_analysis: InvoiceAnalysis
    enhanced_analysis: InvoiceAnalysis
    original_score: int
    enhanced_score: int
    winner: Winner


def compare_readings(
    original: ExtractedInvoice, enhanced: ExtractedInvoice, own_cif: str
) -> ComparisonVerdict:
    """Puntúa ambas lecturas con el análisis de dominio ya auditado de S2.3 y decide el ganador."""
    original_analysis = analyze_invoice(original, own_cif)
    enhanced_analysis = analyze_invoice(enhanced, own_cif)
    original_score = score_analysis(original_analysis)
    enhanced_score = score_analysis(enhanced_analysis)

    winner: Winner
    if enhanced_score > original_score:
        winner = "enhanced"
    elif original_score > enhanced_score:
        winner = "original"
    else:
        winner = "tie"

    return ComparisonVerdict(
        original_analysis=original_analysis,
        enhanced_analysis=enhanced_analysis,
        original_score=original_score,
        enhanced_score=enhanced_score,
        winner=winner,
    )
