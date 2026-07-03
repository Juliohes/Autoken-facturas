"""Runner del bench OCR (1.2): corre motores de lectura sobre el dataset y saca la tabla.

Se ejecuta A MANO (usa las API keys del `.env` y llama a las APIs reales). Para cada factura con
ground truth, corre cada motor, puntúa el recall de lectura y agrega por motor.

Uso (desde `backend/`, con el venv activado):
    python scripts/run_ocr_bench.py
    python scripts/run_ocr_bench.py --engines mistral-ocr-4   # subconjunto

Por ahora el único motor cableado es Mistral OCR 4 (cabeza de serie). Los siguientes se añaden en
`_build_engines` a medida que tengan su adaptador.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ocr.engines import build_default_reading_engine, build_docintel_engine
from ocr.engines.base import OcrEngine
from ocr.engines.base import OcrError as _OcrError
from ocr.eval import aggregate_by_engine, load_ground_truth, score_reading
from shared.config import get_settings

_GROUND_TRUTH_DIR = Path(__file__).resolve().parents[2] / "docs" / "ocr-eval" / "ground-truth"
_FACTURAS_DIR = Path(__file__).resolve().parents[2] / "entregas" / "facturas"


def _build_engines(names: set[str] | None) -> dict[str, OcrEngine]:
    """Construye los motores con credenciales disponibles. Luego: Gemini, Claude, gpt-5.1."""
    settings = get_settings()
    builders = (build_default_reading_engine, build_docintel_engine)
    available: dict[str, OcrEngine] = {}
    for builder in builders:
        try:
            engine = builder(settings)
        except _OcrError as exc:  # sin credenciales: se omite ese motor, no se cae el bench
            print(f"  (motor omitido: {exc})")
            continue
        available[engine.name] = engine
    if names is None:
        return available
    return {name: engine for name, engine in available.items() if name in names}


async def _run(engine_names: set[str] | None) -> int:
    ground_truth = load_ground_truth(_GROUND_TRUTH_DIR)
    if not ground_truth:
        print(f"No hay ground truth en {_GROUND_TRUTH_DIR}. Genera los JSON primero.")
        return 1

    engines = _build_engines(engine_names)
    if not engines:
        print("Ningún motor seleccionado.")
        return 1

    print(f"Facturas: {len(ground_truth)} · motores: {', '.join(engines)}\n")
    scores = []
    for gt in ground_truth:
        source = _FACTURAS_DIR / gt.source_file
        for engine in engines.values():
            try:
                result = await engine.extract(source)
            except Exception as exc:  # el bench no se cae por una factura/motor concreto
                print(f"  [{engine.name}] {gt.invoice_id}: ERROR {exc}")
                continue
            score = score_reading(gt, result.text, engine=engine.name)
            scores.append(score)
            print(f"  [{engine.name}] {gt.invoice_id}: recall {score.recall:.0%}")

    print("\n=== Agregado por motor ===")
    print(f"{'motor':<20} {'facturas':>8} {'recall':>8} {'recall CIF':>11}")
    for agg in aggregate_by_engine(scores).values():
        print(f"{agg.engine:<20} {agg.invoices:>8} {agg.recall:>7.0%} {agg.tax_id_recall:>10.0%}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bench de motores de lectura OCR (tarea 1.2)")
    parser.add_argument("--engines", nargs="*", help="motores a correr (por defecto todos)")
    args = parser.parse_args()
    names = set(args.engines) if args.engines else None
    return asyncio.run(_run(names))


if __name__ == "__main__":
    raise SystemExit(main())
