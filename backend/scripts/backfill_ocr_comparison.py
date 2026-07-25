"""CLI del backfill retroactivo de la comparativa original-vs-realzada (S2.10).

Por defecto corre en modo SIMULACIÓN (activo salvo que se pase `--execute`): lista los ficheros
candidatos sin invocar al lector de IA ni escribir nada. El modo real (`--execute`) SÍ dispara
llamadas de pago a la API del lector — dos por factura — sobre el histórico completo de todos los
tenants; es una decisión de coste real que corresponde a Julio, nunca el comportamiento por defecto.
Throttle configurable (`--rate-limit-seconds`, por defecto 1s) entre facturas en modo real.

La lógica vive en `jobs.ocr_backfill` (testable sin CLI); este fichero es solo el envoltorio de
línea de comandos.

Uso (desde `backend/`, con el venv activado):
    python scripts/backfill_ocr_comparison.py                      # simulación (no toca nada)
    python scripts/backfill_ocr_comparison.py --execute             # ejecución real
    python scripts/backfill_ocr_comparison.py --execute --rate-limit-seconds 3
"""

from __future__ import annotations

import argparse
import asyncio

from jobs.ocr_backfill import run_backfill


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Ejecuta de verdad (llamadas de pago reales). Sin esta flag: solo simulación.",
    )
    parser.add_argument(
        "--rate-limit-seconds",
        type=float,
        default=1.0,
        help="Segundos de espera entre facturas en modo --execute (por defecto 1s).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summary = asyncio.run(
        run_backfill(execute=args.execute, rate_limit_seconds=args.rate_limit_seconds)
    )
    mode = "ejecución real" if args.execute else "simulación"
    print(
        f"Backfill ({mode}): {summary.candidates} candidatos, "
        f"{summary.processed} procesados, {summary.failed} fallidos."
    )


if __name__ == "__main__":
    main()
