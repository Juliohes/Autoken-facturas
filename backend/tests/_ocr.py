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

import io
from datetime import date
from decimal import Decimal
from uuid import uuid4

import asyncpg
from PIL import Image

from invoice_intake import storage
from tests._intake import JPEG, JPEG_CT

# CIF propio de la empresa (en `companies`) y CIF de contraparte, ambos válidos mód-23.
OWN_CIF = "B06183446"
COUNTERPARTY_CIF = "A39031620"
# CIF con dígito de control inválido (para C5): mismo número, letra de control equivocada.
INVALID_COUNTERPARTY_CIF = "A39031621"


def real_jpeg_bytes() -> bytes:
    """Un JPEG de verdad (decodificable por Pillow), a diferencia de `tests._intake.JPEG` (un
    fixture mínimo que basta para el resto del pipeline OCR, que nunca decodifica la imagen). La
    comparativa de S2.10 SÍ la decodifica para realzarla (S2.9), así que los tests que la ejercitan
    de extremo a extremo necesitan una imagen real."""
    image = Image.new("RGB", (100, 60), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


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
    engine: str = "fake",
    model: str = "fake-1",
):
    """Construye un `ExtractedInvoice` de prueba (import perezoso de los tipos de producción).

    Por defecto: factura legible y coherente (own presente, contraparte válida, cuadre OK, alto).
    Los tests sobreescriben el campo que quieren romper. `own_cif=None` -> el CIF propio no aparece
    (C4); `counterparty_cif=None` -> contraparte no legible (C2). `engine`/`model`: identidad del
    motor (S4.8, ranking multi-modelo — distinguir varios motores dobles entre sí)."""
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
        engine=engine,
        model=model,
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


def make_counting_extractor(invoice):
    """Extractor doble que cuenta cuántas veces se llama `.extract()` (regresión S4.8: el motor por
    defecto no debe llamarse dos veces por factura cuando el ranking multi-modelo reutiliza la
    lectura ya calculada — ver `jobs.ocr.run_ocr`/`jobs.ocr_ranking.run_ocr_ranking`)."""

    class _CountingExtractor:
        def __init__(self) -> None:
            self.calls = 0

        async def extract(self, content: bytes, content_type: str):  # noqa: ARG002
            self.calls += 1
            return invoice

    return _CountingExtractor()


def make_comparison_extractor(*, original, enhanced, error_on: str | None = None):
    """Doble content-type-aware para S2.10 (C2/C5/C6/C7): distingue la llamada "original" de la
    "realzada" por el `content_type` recibido, sin depender de bytes reales ni de un motor real.

    El realce (`ocr.preprocess.enhance.enhance_invoice_image`) siempre produce `image/png` — esa
    es la señal que usa este doble para saber qué lectura devolver. `error_on`
    ("original" | "enhanced") simula que esa llamada en concreto falla (C5), la otra intacta.
    """
    from ocr.extraction import InvoiceExtractionError
    from ocr.preprocess.enhance import ENHANCED_CONTENT_TYPE

    class _ComparisonExtractor:
        async def extract(self, content: bytes, content_type: str):  # noqa: ARG002
            is_enhanced_call = content_type == ENHANCED_CONTENT_TYPE
            if error_on == "enhanced" and is_enhanced_call:
                raise InvoiceExtractionError("fallo simulado de la lectura realzada")
            if error_on == "original" and not is_enhanced_call:
                raise InvoiceExtractionError("fallo simulado de la lectura original")
            return enhanced if is_enhanced_call else original

    return _ComparisonExtractor()


async def run_ocr(
    *, tenant_id: str, company_id: str, file_id: str, extractor, ranking_extractors
) -> None:
    """Invoca el job del worker directamente (import perezoso; sin arq corriendo).

    `ranking_extractors` es OBLIGATORIO (sin default): pásalo siempre explícito, aunque sea `[]`.
    Dejarlo con un default en `None` fue precisamente el incidente real durante el desarrollo de
    S4.8 — un test con el interruptor encendido llamó a `run_ocr` sin pasarlo y `run_ocr` construyó
    los motores reales desde la config, disparando llamadas de pago de verdad en un entorno con
    credenciales reales configuradas (ver docstring de `jobs.ocr.run_ocr`). Quitarle el default aquí
    obliga a cada test a decidir explícitamente qué motores usar.
    """
    from jobs.ocr import run_ocr as _run

    await _run(
        tenant_id, company_id, file_id, extractor=extractor, ranking_extractors=ranking_extractors
    )


async def set_ocr_experiment_enabled(dsns: dict[str, str], enabled: bool) -> None:
    """Enciende/apaga el interruptor admin-tech (S4.10) directamente en BD (superusuario).

    La fila única de `platform_settings` ya existe (la inserta la migración 0017); aquí solo se
    actualiza, sin pasar por el endpoint HTTP (ese camino ya lo prueba `test_platform_settings.py`).
    """
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "UPDATE platform_settings SET ocr_experiment_enabled = $1 WHERE id = true", enabled
        )
    finally:
        await conn.close()


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


# --- Consultas de efecto de la comparativa S2.10 (superusuario, saltando RLS) ----------------
async def fetch_comparison_run(dsns: dict[str, str], *, file_id: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT * FROM ocr_comparison_runs WHERE uploaded_file_id = $1", file_id
        )
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def count_comparison_runs(dsns: dict[str, str], *, file_id: str) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(
            await conn.fetchval(
                "SELECT count(*) FROM ocr_comparison_runs WHERE uploaded_file_id = $1", file_id
            )
        )
    finally:
        await conn.close()


async def comparison_runs_visible_as_tenant(
    dsns: dict[str, str], *, tenant_id: str, company_id: str | None = None
) -> int:
    """Igual que `extractions_visible_as_tenant`, pero sobre `ocr_comparison_runs` (C9)."""
    conn = await asyncpg.connect(dsns["app"])
    try:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", tenant_id)
        await conn.execute(
            "SELECT set_config('app.company_id', $1, false)", company_id if company_id else ""
        )
        return int(await conn.fetchval("SELECT count(*) FROM ocr_comparison_runs"))
    finally:
        await conn.close()


# --- Consultas de efecto del ranking multi-modelo S4.8 (superusuario, saltando RLS) ----------
async def seed_ranking_entry(
    dsns: dict[str, str],
    *,
    tenant_id: str,
    company_id: str,
    uploaded_file_id: str,
    engine: str,
    score: int,
    model: str = "modelo-de-prueba",
) -> None:
    """Inserta directamente una fila de `ocr_ranking_entries` (superusuario), como recomienda la
    spec S4.8 §7 para probar la agregación del panel (C11) sin depender de motores reales."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "INSERT INTO ocr_ranking_entries "
            "(tenant_id, company_id, uploaded_file_id, engine, model, reading, score) "
            "VALUES ($1,$2,$3,$4,$5,'{}'::jsonb,$6) "
            "ON CONFLICT (uploaded_file_id, engine) DO UPDATE SET score = EXCLUDED.score",
            tenant_id,
            company_id,
            uploaded_file_id,
            engine,
            model,
            score,
        )
    finally:
        await conn.close()


async def fetch_ranking_entries(dsns: dict[str, str], *, file_id: str) -> list[dict]:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        rows = await conn.fetch(
            "SELECT * FROM ocr_ranking_entries WHERE uploaded_file_id = $1 ORDER BY engine", file_id
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def count_ranking_entries(dsns: dict[str, str], *, file_id: str) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(
            await conn.fetchval(
                "SELECT count(*) FROM ocr_ranking_entries WHERE uploaded_file_id = $1", file_id
            )
        )
    finally:
        await conn.close()


async def ranking_entries_visible_as_tenant(
    dsns: dict[str, str], *, tenant_id: str, company_id: str | None = None
) -> int:
    """Igual que `extractions_visible_as_tenant`, pero sobre `ocr_ranking_entries` (C9)."""
    conn = await asyncpg.connect(dsns["app"])
    try:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", tenant_id)
        await conn.execute(
            "SELECT set_config('app.company_id', $1, false)", company_id if company_id else ""
        )
        return int(await conn.fetchval("SELECT count(*) FROM ocr_ranking_entries"))
    finally:
        await conn.close()
