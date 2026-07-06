"""Runner del bench OCR (1.2): corre motores de lectura sobre el dataset y saca la tabla + JSON.

Se ejecuta A MANO (usa las API keys del `.env` y llama a las APIs reales). Para cada factura con
ground truth, corre cada motor, mide **latencia**, captura el **uso/tokens** que devuelve el
proveedor (para estimar coste) y puntúa el **recall de lectura** (global, por campo y específico
de identificadores fiscales, §11.8). Agrega por motor y vuelca un artefacto JSON reproducible que
alimenta el informe `docs/ocr-eval/resultado-poc.md` y el ADR-0007.

Uso (desde `backend/`, con el venv activado):
    python scripts/run_ocr_bench.py                      # todos los motores con credenciales
    python scripts/run_ocr_bench.py --engines gpt-5.1    # subconjunto
    python scripts/run_ocr_bench.py --out ../docs/ocr-eval/results/bench.json

Cada motor sin credenciales en el `.env` se omite con un aviso; un fallo puntual (una factura, un
motor) no tumba el bench: se registra como error y se sigue.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ocr.engines import (
    build_azure_openai_engine,
    build_claude_engine,
    build_default_reading_engine,
    build_docintel_engine,
    build_gemini_engines,
)
from ocr.engines.base import OcrEngine
from ocr.engines.base import OcrError as _OcrError
from ocr.eval import (
    ReadingScore,
    aggregate_by_engine,
    field_recall_by_engine,
    load_ground_truth,
    score_reading,
)
from shared.config import get_settings

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GROUND_TRUTH_DIR = _REPO_ROOT / "docs" / "ocr-eval" / "ground-truth"
_FACTURAS_DIR = _REPO_ROOT / "entregas" / "facturas"
_DEFAULT_OUT = _REPO_ROOT / "docs" / "ocr-eval" / "results" / "bench-latest.json"


@dataclass
class _Record:
    """Una medición: un motor sobre una factura (o su error)."""

    engine: str
    invoice_id: str
    recall: float | None = None
    tax_id_recall: float | None = None
    latency_s: float | None = None
    usage: dict[str, Any] | None = None
    error: str | None = None
    text: str | None = None  # texto crudo del motor: permite RE-PUNTUAR offline sin llamar a la API
    scored: ReadingScore | None = None  # para el agregado por campo


def _build_engines(names: set[str] | None) -> dict[str, OcrEngine]:
    """Construye los motores con credenciales disponibles (los 6 candidatos del bench).

    Cada builder devuelve uno o varios motores (Gemini aporta Flash y Pro). Un builder cuyo motor
    no tenga credenciales lanza `OcrError` y se omite entero, sin caer el bench.
    """
    settings = get_settings()
    builders = (
        build_default_reading_engine,
        build_docintel_engine,
        build_gemini_engines,
        build_azure_openai_engine,
        build_claude_engine,
    )
    available: dict[str, OcrEngine] = {}
    for builder in builders:
        try:
            built = builder(settings)
        except _OcrError as exc:  # sin credenciales: se omite ese motor, no se cae el bench
            print(f"  (motor omitido: {exc})")
            continue
        for engine in built if isinstance(built, list) else [built]:
            available[engine.name] = engine
    if names is None:
        return available
    return {name: engine for name, engine in available.items() if name in names}


def _tax_id_recall(scored: ReadingScore) -> float | None:
    """Recall de solo los CIF/NIF de una puntuación (o None si la factura no traía ninguno)."""
    tax = [r for r in scored.results if r.field == "tax_id"]
    if not tax:
        return None
    return sum(r.found for r in tax) / len(tax)


async def _measure(engine: OcrEngine, gt: Any) -> _Record:
    """Corre un motor sobre una factura midiendo latencia y capturando uso; nunca lanza."""
    source = _FACTURAS_DIR / gt.source_file
    started = time.perf_counter()
    try:
        result = await engine.extract(source)
    except Exception as exc:  # el bench no se cae por una factura/motor concreto
        return _Record(engine.name, gt.invoice_id, error=str(exc))
    latency = time.perf_counter() - started
    score = score_reading(gt, result.text, engine=engine.name)
    return _Record(
        engine=engine.name,
        invoice_id=gt.invoice_id,
        recall=score.recall,
        tax_id_recall=_tax_id_recall(score),
        latency_s=round(latency, 3),
        usage=result.usage,
        text=result.text,
        scored=score,
    )


def _usage_totals(records: list[_Record]) -> dict[str, float]:
    """Suma las claves numéricas de primer nivel del `usage` (tokens/páginas) de un motor."""
    totals: dict[str, float] = {}
    for rec in records:
        for key, value in (rec.usage or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return totals


def _aggregate(records: list[_Record]) -> dict[str, Any]:
    """Construye el agregado por motor: recall global/CIF/por-campo, latencia, uso y errores."""
    scores = [r.scored for r in records if r.scored is not None]
    by_engine_recall = aggregate_by_engine(scores)
    by_engine_fields = field_recall_by_engine(scores)

    by_engine: dict[str, list[_Record]] = {}
    for rec in records:
        by_engine.setdefault(rec.engine, []).append(rec)

    out: dict[str, Any] = {}
    for engine, recs in by_engine.items():
        ok = [r for r in recs if r.error is None]
        latencies = [r.latency_s for r in ok if r.latency_s is not None]
        errors = [{"invoice_id": r.invoice_id, "error": r.error} for r in recs if r.error]
        agg = by_engine_recall.get(engine)
        out[engine] = {
            "invoices_scored": len(ok),
            "invoices_failed": len(errors),
            "recall": round(agg.recall, 4) if agg else None,
            "tax_id_recall": round(agg.tax_id_recall, 4) if agg else None,
            "field_recall": {k: round(v, 4) for k, v in by_engine_fields.get(engine, {}).items()},
            "latency_s": {
                "mean": round(statistics.fmean(latencies), 3) if latencies else None,
                "median": round(statistics.median(latencies), 3) if latencies else None,
                "max": max(latencies) if latencies else None,
            },
            "usage_totals": _usage_totals(ok),
            "errors": errors,
        }
    return out


async def _run(engine_names: set[str] | None, out_path: Path) -> int:
    ground_truth = load_ground_truth(_GROUND_TRUTH_DIR)
    if not ground_truth:
        print(f"No hay ground truth en {_GROUND_TRUTH_DIR}. Genera los JSON primero.")
        return 1

    engines = _build_engines(engine_names)
    if not engines:
        print("Ningún motor seleccionado.")
        return 1

    print(f"Facturas: {len(ground_truth)} · motores: {', '.join(engines)}\n")
    records: list[_Record] = []
    for gt in ground_truth:
        for engine in engines.values():
            rec = await _measure(engine, gt)
            records.append(rec)
            if rec.error:
                print(f"  [{engine.name}] {gt.invoice_id}: ERROR {rec.error[:90]}")
            else:
                print(
                    f"  [{engine.name}] {gt.invoice_id}: "
                    f"recall {rec.recall:.0%}  {rec.latency_s}s"
                )

    aggregate = _aggregate(records)
    _print_table(aggregate)
    _write_json(out_path, ground_truth, engines, aggregate, records)
    print(f"\nArtefacto JSON: {out_path}")
    return 0


def _print_table(aggregate: dict[str, Any]) -> None:
    print("\n=== Agregado por motor ===")
    cols = ("motor", "facturas", "recall", "CIF", "fecha", "total", "lat.s")
    print(f"{cols[0]:<18}{cols[1]:>9}{cols[2]:>8}{cols[3]:>7}{cols[4]:>7}{cols[5]:>7}{cols[6]:>8}")
    for engine, agg in sorted(aggregate.items(), key=lambda kv: -(kv[1]["recall"] or 0)):
        fr = agg["field_recall"]
        lat = agg["latency_s"]["mean"]
        print(
            f"{engine:<18}"
            f"{agg['invoices_scored']:>9}"
            f"{_pct(agg['recall']):>8}"
            f"{_pct(agg['tax_id_recall']):>7}"
            f"{_pct(fr.get('issue_date')):>7}"
            f"{_pct(fr.get('total_amount')):>7}"
            f"{(f'{lat:.1f}' if lat is not None else '-'):>8}"
        )


def _pct(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "-"


def _write_json(
    out_path: Path,
    ground_truth: tuple[Any, ...],
    engines: dict[str, OcrEngine],
    aggregate: dict[str, Any],
    records: list[_Record],
) -> None:
    """Vuelca el resultado completo a JSON (reproducible, alimenta informe y ADR-0007)."""
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": {
            "invoices": len(ground_truth),
            "dir": str(_FACTURAS_DIR.relative_to(_REPO_ROOT)),
        },
        "engines_run": sorted(engines),
        "aggregate": aggregate,
        "per_invoice": [
            {
                "engine": r.engine,
                "invoice_id": r.invoice_id,
                "recall": r.recall,
                "tax_id_recall": r.tax_id_recall,
                "latency_s": r.latency_s,
                "usage": r.usage,
                "error": r.error,
                "text": r.text,
            }
            for r in records
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bench de motores de lectura OCR (tarea 1.2)")
    parser.add_argument("--engines", nargs="*", help="motores a correr (por defecto todos)")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="ruta del artefacto JSON")
    args = parser.parse_args()
    names = set(args.engines) if args.engines else None
    return asyncio.run(_run(names, args.out))


if __name__ == "__main__":
    raise SystemExit(main())
