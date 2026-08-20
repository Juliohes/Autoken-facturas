"""Experimento Frente B (S6.15 hermano): pipeline Mistral OCR (texto) + estructurador LLM.

Idea: Mistral OCR 4 es el motor más rápido medido (4,2s de media) pero NO extrae campos
estructurados (devuelve markdown). Un LLM pequeño estructurando TEXTO (sin imagen) es mucho más
rápido que ese mismo LLM leyendo la IMAGEN, porque el prefill de imagen (tiles) es lo caro.

Hipótesis a medir: Mistral(texto) + Gemini-Flash-estructura-texto ~= 4s + ~2-4s = ~7s total, muy
por debajo de los 15,3s de Gemini-Flash-sobre-imagen, con precisión comparable.

Este script NO toca producción: lee las facturas confirmadas de un tenant, corre el pipeline de 2
saltos sobre sus imágenes reales de MinIO, y compara contra la factura confirmada (verdad). Imprime
tiempos por fase y acierto por campo. NO persiste nada en las tablas de ranking/benchmark.

Uso (desde `backend/`, con el .env real cargado y credenciales de Mistral + Vertex):
    REDIS_URL=... .venv/bin/python scripts/experiment_mistral_pipeline.py \
        --tenant-id <uuid> --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@dataclass
class PhaseTiming:
    ocr_s: float = 0.0
    structure_s: float = 0.0

    @property
    def total_s(self) -> float:
        return self.ocr_s + self.structure_s


def _markdown_from_mistral(raw: dict) -> str:
    """Concatena el markdown de todas las páginas que devolvió Mistral (el texto crudo leído)."""
    pages = raw.get("pages") or []
    parts = [page.get("markdown") or "" for page in pages]
    return "\n\n".join(p for p in parts if p)


_STRUCTURE_PROMPT = (
    "Eres un extractor de datos de facturas españolas. A continuación va el TEXTO (markdown) leído "
    "por OCR de una factura. Extrae los campos y responde SOLO con un JSON válido con esta forma "
    "exacta (null si un dato no es legible):\n"
    '{"issue_date": "AAAA-MM-DD"|null, "total_amount": number|null, "net_amount": number|null, '
    '"tax_amount": number|null, "invoice_number": string|null, '
    '"tax_lines": [{"base": number, "rate": number, "cuota": number}], '
    '"tax_ids": [{"value": "CIF/NIF"|null, "name": string|null, '
    '"value_confidence": "alta"|"media"|"baja", "name_confidence": "alta"|"media"|"baja"}]}\n'
    "Reglas: transcribe fielmente los identificadores fiscales (CIF/NIF) y el número de factura; "
    "si un dato no está en el texto, ponlo a null. No inventes valores. Prioriza la razón social "
    "LEGAL junto al CIF/NIF sobre un nombre comercial o logo.\n\nTEXTO DE LA FACTURA:\n"
)


async def _structure_text_with_gemini(markdown: str, settings) -> object:
    """Estructura el TEXTO de Mistral con Gemini Flash (sin imagen: prefill barato, rápido)."""
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.gemini_location,
    )
    prompt = _STRUCTURE_PROMPT + markdown
    response = await client.aio.models.generate_content(
        model=settings.gemini_flash_model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "temperature": 0,
        },
    )
    return response


async def _run_one(mistral, settings, content: bytes, content_type: str) -> tuple[object, PhaseTiming, str]:
    """Corre el pipeline de 2 saltos sobre una imagen; devuelve (lectura, tiempos, markdown)."""
    from ocr.engines.mistral_extractor import MistralInvoiceExtractor
    from ocr.extraction_json import parse_structured_invoice

    timing = PhaseTiming()

    # Salto 1: Mistral OCR (imagen -> markdown). Reutilizamos el extractor real para la llamada,
    # pero leemos el markdown crudo de su `raw` (los campos estructurados vienen vacíos por diseño).
    t0 = time.monotonic()
    assert isinstance(mistral, MistralInvoiceExtractor)
    empty_reading = await mistral.extract(content, content_type)
    timing.ocr_s = time.monotonic() - t0
    markdown = _markdown_from_mistral(empty_reading.raw or {})

    if not markdown.strip():
        return empty_reading, timing, markdown

    # Salto 2: Gemini Flash estructura el TEXTO (sin imagen).
    t1 = time.monotonic()
    response = await _structure_text_with_gemini(markdown, settings)
    timing.structure_s = time.monotonic() - t1

    reading = parse_structured_invoice(
        getattr(response, "text", None), engine="mistral+gemini-text", model=settings.gemini_flash_model
    )
    return reading, timing, markdown


def _score(reading, truth: dict) -> dict[str, bool]:
    """Acierto campo a campo contra la factura confirmada (verdad humana)."""

    def money_eq(a, b) -> bool:
        if a is None or b is None:
            return False
        try:
            return abs(Decimal(str(a)) - Decimal(str(b))) < Decimal("0.02")
        except Exception:
            return False

    def norm(s) -> str:
        return "".join(ch for ch in str(s or "").upper() if ch.isalnum())

    counterparty = None
    for tid in getattr(reading, "tax_ids", ()) or ():
        if tid.value and norm(tid.value) != norm(truth.get("own_cif")):
            counterparty = tid
            break

    return {
        "issue_date": str(getattr(reading, "issue_date", None) or "") == str(truth.get("issue_date") or ""),
        "total_amount": money_eq(getattr(reading, "total_amount", None), truth.get("total_amount")),
        "invoice_number": norm(getattr(reading, "invoice_number", None)) == norm(truth.get("invoice_number")),
        "counterparty_cif": counterparty is not None and norm(counterparty.value) == norm(truth.get("counterparty_tax_id")),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    from shared.config import get_settings
    from shared.db import tenant_session
    from invoice_intake import repository as intake_repo
    from invoice_intake import storage
    from invoicing import repository as invoicing_repo
    from shared.encryption import tenant_encryption_key
    from ocr.engines.mistral_extractor import build_mistral_extractor

    settings = get_settings()
    mistral = build_mistral_extractor(settings)
    tenant_id = UUID(args.tenant_id)

    async with tenant_session(tenant_id, None) as session:  # type: ignore[arg-type]
        # Facturas confirmadas con fichero, las más recientes primero. Las columnas
        # cifradas (S5.2) se descifran con la clave del tenant (hex, contraseña de pgcrypto).
        from sqlalchemy import text as _text
        rows = (await session.execute(_text(
            """
            SELECT i.id, i.uploaded_file_id, i.company_id, i.issue_date, i.total_amount,
                   i.invoice_number,
                   pgp_sym_decrypt(i.counterparty_tax_id, :k)::text AS counterparty_tax_id,
                   c.cif_owner AS own_cif
            FROM invoices i
            JOIN uploaded_files uf ON uf.id = i.uploaded_file_id
            JOIN LATERAL (SELECT pgp_sym_decrypt(c2.cif, :k)::text AS cif_owner FROM companies c2
                          WHERE c2.id = i.company_id) c ON true
            ORDER BY i.created_at DESC
            LIMIT :lim
            """
        ), {"k": tenant_encryption_key(settings, tenant_id), "lim": args.limit})).fetchall()

    if not rows:
        print("No hay facturas confirmadas para ese tenant.")
        return

    print(f"Evaluando {len(rows)} facturas con pipeline Mistral(texto)+Gemini(estructura)...\n")
    timings: list[PhaseTiming] = []
    field_hits: dict[str, int] = {"issue_date": 0, "total_amount": 0, "invoice_number": 0, "counterparty_cif": 0}
    n_scored = 0

    for row in rows:
        file_id = row.uploaded_file_id
        company_id = row.company_id
        async with tenant_session(tenant_id, company_id) as session:
            locations = await intake_repo.get_document_pages(session, file_id)
        if not locations:
            continue
        content = await asyncio.to_thread(storage.get_object, locations[0].bucket, locations[0].key)
        content_type = locations[0].content_type

        truth = {
            "issue_date": row.issue_date,
            "total_amount": row.total_amount,
            "invoice_number": row.invoice_number,
            "counterparty_tax_id": row.counterparty_tax_id,
            "own_cif": row.own_cif,
        }
        try:
            reading, timing, markdown = await _run_one(mistral, settings, content, content_type)
        except Exception as exc:  # noqa: BLE001 - experimento: registrar y seguir
            print(f"  [fallo] {file_id}: {type(exc).__name__}: {exc}")
            continue

        timings.append(timing)
        hits = _score(reading, truth)
        n_scored += 1
        for k, v in hits.items():
            field_hits[k] += 1 if v else 0
        print(
            f"  {file_id} | ocr={timing.ocr_s:.1f}s estructura={timing.structure_s:.1f}s "
            f"total={timing.total_s:.1f}s | aciertos: "
            + ", ".join(f"{k}={'OK' if v else 'X'}" for k, v in hits.items())
        )

    if timings:
        ocr = [t.ocr_s for t in timings]
        struct = [t.structure_s for t in timings]
        total = [t.total_s for t in timings]
        print("\n=== TIEMPOS (s) ===")
        print(f"  Mistral OCR (texto):      media={statistics.mean(ocr):.1f}  mediana={statistics.median(ocr):.1f}")
        print(f"  Gemini estructura texto:  media={statistics.mean(struct):.1f}  mediana={statistics.median(struct):.1f}")
        print(f"  TOTAL 2 saltos:           media={statistics.mean(total):.1f}  mediana={statistics.median(total):.1f}")
        print(f"\n=== ACIERTO (sobre {n_scored} facturas) ===")
        for k, v in field_hits.items():
            pct = 100.0 * v / n_scored if n_scored else 0
            print(f"  {k:18} {v}/{n_scored}  ({pct:.0f}%)")
        print("\nReferencia producción (Gemini Flash sobre imagen): ~15,3s media.")


if __name__ == "__main__":
    asyncio.run(main())
