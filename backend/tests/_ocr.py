"""Utilidades de test para el worker OCR (S2.3, spec docs/specs/S2.3-worker-ocr.md).

No es un módulo de tests (prefijo `_`): siembra de un `uploaded_file` (fila + objeto en MinIO),
un extractor doble inyectable, un constructor de `ExtractedInvoice` de prueba, y consultas de
efecto sobre `ocr_extractions` y el estado del `uploaded_file`.

Contrato que el `implementer` debe respetar (lo fija esta fase roja):
- Job del worker: `jobs.ocr.run_ocr(tenant_id, company_id, uploaded_file_id, *, extractor)`
  (coroutine invocable directa en test; sin arq). Fija el contexto de tenant (RLS) desde los ids.
- Extractor: `ocr.extraction.InvoiceExtractor` con `async extract(content, content_type)`
  -> `ExtractedInvoice`; lanza `ocr.extraction.InvoiceExtractionError` ante fallo del proveedor.
  Tipos: `ExtractedInvoice`, `ExtractedTaxId(value, name, confidence)`,
  `ExtractedTaxLine(base, rate, cuota)`;
  `confidence` ∈ {"alta","media","baja"}; un campo no legible = `value` None.
- Persistencia: tabla `ocr_extractions` (una vigente por `uploaded_file_id`), RLS de dos niveles.
- Estados del `uploaded_file`: `pending_ocr` -> `ocr_done` (todo alto y válido) / `needs_review`
  (dudoso/no leído/validación KO/CIF propio ausente) / `ocr_failed` (el extractor falló).
- Contraparte = el identificador leído que NO es el CIF propio (propio conocido desde `companies`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import asyncpg

from invoice_intake import storage
from tests._intake import JPEG, JPEG_CT

# CIF propio de la empresa (en `companies`) y CIF de contraparte, ambos válidos mód-23.
OWN_CIF = "B06183446"
COUNTERPARTY_CIF = "A39031620"
# CIF con dígito de control inválido (para C5): mismo número, letra de control equivocada.
INVALID_COUNTERPARTY_CIF = "A39031621"


async def seed_uploaded_file(
    dsns: dict[str, str],
    *,
    tenant_id: str,
    company_id: str,
    uploaded_by: str,
    content: bytes = JPEG,
    content_type: str = JPEG_CT,
    status: str = "pending_ocr",
) -> str:
    """Sube el objeto a MinIO e inserta la fila `uploaded_files`. Devuelve el id del fichero.

    Usa las convenciones de S2.1 (`storage.bucket_for`/`key_for`) para que el worker lo localice.
    """
    import hashlib

    sha256 = hashlib.sha256(content).hexdigest()
    bucket = storage.bucket_for(tenant_id)
    key = storage.key_for(company_id, sha256)
    storage.put_object(bucket, key, content, len(content), content_type)

    file_id = str(uuid4())
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "INSERT INTO uploaded_files (id, tenant_id, company_id, uploaded_by, storage_bucket, "
            "storage_key, content_type, size_bytes, sha256, status, scan_status) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'clean')",
            file_id,
            tenant_id,
            company_id,
            uploaded_by,
            bucket,
            key,
            content_type,
            len(content),
            sha256,
            status,
        )
        return file_id
    finally:
        await conn.close()


def build_extracted(
    *,
    own_cif: str | None = OWN_CIF,
    own_name: str = "Mi Empresa SL",
    counterparty_cif: str | None = COUNTERPARTY_CIF,
    counterparty_name: str | None = "Proveedor SA",
    counterparty_conf: str = "alta",
    issue_date: date | None = date(2026, 5, 10),
    net: Decimal | None = Decimal("100.00"),
    tax: Decimal | None = Decimal("21.00"),
    total: Decimal | None = Decimal("121.00"),
    rate: Decimal = Decimal("21"),
    confidence: str = "alta",
):
    """Construye un `ExtractedInvoice` de prueba (import perezoso de los tipos de producción).

    Por defecto: factura legible y coherente (own presente, contraparte válida, cuadre OK, alto).
    Los tests sobreescriben el campo que quieren romper. `own_cif=None` -> el CIF propio no aparece
    (C4); `counterparty_cif=None` -> contraparte no legible (C2).
    """
    from ocr.extraction import ExtractedInvoice, ExtractedTaxId, ExtractedTaxLine

    tax_ids: list = []
    if own_cif is not None:
        tax_ids.append(ExtractedTaxId(value=own_cif, name=own_name, confidence="alta"))
    if counterparty_cif is not None:
        tax_ids.append(
            ExtractedTaxId(
                value=counterparty_cif, name=counterparty_name, confidence=counterparty_conf
            )
        )
    tax_lines = (
        (ExtractedTaxLine(base=net, rate=rate, cuota=tax),)
        if net is not None and tax is not None
        else ()
    )
    return ExtractedInvoice(
        issue_date=issue_date,
        issue_date_confidence=confidence,
        total_amount=total,
        total_confidence=confidence,
        net_amount=net,
        tax_amount=tax,
        tax_lines=tax_lines,
        tax_ids=tuple(tax_ids),
        engine="fake",
        model="fake-1",
        raw={},
    )


def make_extractor(invoice=None, *, error: Exception | None = None):
    """Extractor doble: devuelve `invoice` (o lanza `error`) sin llamar a ningún proveedor real."""

    class _FakeExtractor:
        async def extract(self, content: bytes, content_type: str):  # noqa: ARG002
            if error is not None:
                raise error
            return invoice

    return _FakeExtractor()


async def run_ocr(*, tenant_id: str, company_id: str, file_id: str, extractor) -> None:
    """Invoca el job del worker directamente (import perezoso; sin arq corriendo)."""
    from jobs.ocr import run_ocr as _run

    await _run(tenant_id, company_id, file_id, extractor=extractor)


# --- Consultas de efecto (superusuario, saltando RLS) --------------------------------------------
async def fetch_extraction(dsns: dict[str, str], *, file_id: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT * FROM ocr_extractions WHERE uploaded_file_id = $1", file_id
        )
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def count_extractions(dsns: dict[str, str], *, file_id: str) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(
            await conn.fetchval(
                "SELECT count(*) FROM ocr_extractions WHERE uploaded_file_id = $1", file_id
            )
        )
    finally:
        await conn.close()


async def file_status(dsns: dict[str, str], *, file_id: str) -> str:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return await conn.fetchval("SELECT status FROM uploaded_files WHERE id = $1", file_id)
    finally:
        await conn.close()


async def extractions_visible_as_tenant(
    dsns: dict[str, str], *, tenant_id: str, company_id: str | None = None
) -> int:
    """Cuenta las filas de `ocr_extractions` visibles bajo el ROL RUNTIME en un contexto de tenant.

    Se conecta como `autoken_app` (no superusuario: la RLS aplica) y fija `app.tenant_id`/
    `app.company_id`, igual que hace la app en una petición. Sirve para comprobar el aislamiento.
    """
    conn = await asyncpg.connect(dsns["app"])
    try:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", tenant_id)
        await conn.execute(
            "SELECT set_config('app.company_id', $1, false)", company_id if company_id else ""
        )
        return int(await conn.fetchval("SELECT count(*) FROM ocr_extractions"))
    finally:
        await conn.close()
