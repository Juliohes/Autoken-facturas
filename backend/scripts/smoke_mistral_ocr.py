"""Prueba real (humo) del motor Mistral OCR 4 contra una factura.

Se ejecuta A MANO (no en CI): usa la `MISTRAL_API_KEY` del `.env` y llama a la API real.
El entorno de Claude Code NO lee el `.env`, así que esta validación end-to-end la lanza Julio.

Uso (desde `backend/`, con el venv activado):
    python scripts/smoke_mistral_ocr.py ../entregas/facturas/factura-2.pdf

Imprime el motor/modelo usados, el nº de páginas y un extracto del texto extraído.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ocr.engines import build_default_reading_engine
from shared.config import get_settings


async def _run(file_path: str) -> int:
    settings = get_settings()
    if not settings.mistral_api_key:
        print("ERROR: falta MISTRAL_API_KEY en el .env", file=sys.stderr)
        return 2
    engine = build_default_reading_engine(settings)
    print(f"Motor: {engine.name} · modelo: {settings.mistral_ocr_model}")
    result = await engine.extract(file_path)
    print(f"Páginas: {len(result.pages)} · uso: {result.usage}")
    print("--- extracto del texto (primeros 800 caracteres) ---")
    print(result.text[:800])
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Uso: python {Path(sys.argv[0]).name} <ruta-a-factura>", file=sys.stderr)
        return 2
    return asyncio.run(_run(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
