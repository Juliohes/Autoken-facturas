"""Utilidades de test para el worker OCR (S2.3, spec docs/specs/S2.3-worker-ocr.md).

No es un módulo de tests (prefijo `_`): siembra de un `uploaded_file` (fila + objeto en MinIO),
un extractor doble inyectable, un constructor de `ExtractedInvoice` de prueba, y consultas de
efecto sobre `ocr_extractions` y el estado del `uploaded_file`.

Contrato que el `implementer` debe respetar (lo fija esta fase roja):
- Job del worker: `jobs.ocr.run_ocr(tenant_id, company_id, uploaded_file_id, *, extractor)`
  (coroutine invocable directa en test; sin arq). Fija el contexto de tenant (RLS) desde los ids.
- Extractor: `ocr.extraction.InvoiceExtractor` con `async extract(content, content_type)`
  -> `ExtractedInvoice`; lanza `ocr.extraction.InvoiceExtractionError` ante fallo del proveedor.
  Tipos: `ExtractedInvoice`, `ExtractedTaxId(value, name, value_confidence, name_confidence)`
  (S6.14: confianza del CIF separada de la del nombre), `ExtractedTaxLine(base, rate, cuota)`;
  la confianza ∈ {"alta","media","baja"}; un campo no legible = `value` None.
- Persistencia: tabla `ocr_extractions` (una vigente por `uploaded_file_id`), RLS de dos niveles.
- Estados del `uploaded_file`: `pending_ocr` -> `ocr_done` (todo alto y válido) / `needs_review`
  (dudoso/no leído/validación KO/CIF propio ausente) / `ocr_failed` (el extractor falló) /
  `capture_unreadable` (S6.14: el motor respondió, pero la imagen en sí es el problema).
- Contraparte = el identificador leído que NO es el CIF propio (propio conocido desde `companies`).
"""

from __future__ import annotations

import io
import json
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


async def seed_uploaded_file_page(
    dsns: dict[str, str],
    *,
    tenant_id: str,
    company_id: str,
    root_uploaded_file_id: str,
    page_number: int,
    content: bytes,
    content_type: str = JPEG_CT,
) -> tuple[str, str]:
    """Añade una página secundaria real y devuelve su ubicación de MinIO."""
    import hashlib

    bucket = storage.bucket_for(tenant_id)
    key = storage.key_for(company_id, uuid4())
    storage.put_object(bucket, key, content, len(content), content_type)
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "INSERT INTO uploaded_file_pages "
            "(root_uploaded_file_id, company_id, uploaded_by, page_number, storage_bucket, "
            "storage_key, "
            "content_type, size_bytes, sha256) "
            "SELECT $1,$2,uploaded_by,$3,$4,$5,$6,$7,$8 FROM uploaded_files WHERE id = $1",
            root_uploaded_file_id,
            company_id,
            page_number,
            bucket,
            key,
            content_type,
            len(content),
            hashlib.sha256(content).hexdigest(),
        )
    finally:
        await conn.close()
    return bucket, key


def build_extracted(
    *,
    own_cif: str | None = OWN_CIF,
    own_name: str = "Mi Empresa SL",
    counterparty_cif: str | None = COUNTERPARTY_CIF,
    counterparty_name: str | None = "Proveedor SA",
    counterparty_conf: str = "alta",
    counterparty_value_conf: str | None = None,
    counterparty_name_conf: str | None = None,
    issue_date: date | None = date(2026, 5, 10),
    net: Decimal | None = Decimal("100.00"),
    tax: Decimal | None = Decimal("21.00"),
    total: Decimal | None = Decimal("121.00"),
    rate: Decimal = Decimal("21"),
    irpf_rate: Decimal | None = None,
    irpf_amount: Decimal | None = None,
    irpf_rate_confidence: str | None = None,
    irpf_amount_confidence: str | None = None,
    confidence: str = "alta",
    engine: str = "fake",
    model: str = "fake-1",
    invoice_number: str | None = "F-2026-001",
    invoice_number_confidence: str | None = None,
    net_confidence: str | None = None,
    tax_confidence: str | None = None,
):
    """Construye un `ExtractedInvoice` de prueba (import perezoso de los tipos de producción).

    Por defecto: factura legible y coherente (own presente, contraparte válida, cuadre OK, alto).
    Los tests sobreescriben el campo que quieren romper. `own_cif=None` -> el CIF propio no aparece
    (C4); `counterparty_cif=None` -> contraparte no legible (C2). `engine`/`model`: identidad del
    motor (S4.8, ranking multi-modelo — distinguir varios motores dobles entre sí).

    `invoice_number_confidence`/`net_confidence`/`tax_confidence` caen a `confidence` si no se
    pasan explícitos (spec S6.1, Áreas A/F: número de factura, base imponible e IVA total pasan a
    ser campos de oro con confianza propia, igual que fecha/total).

    `counterparty_value_conf`/`counterparty_name_conf` (S6.14): confianza del CIF y del nombre de
    la contraparte por separado; caen a `counterparty_conf` (mismo valor para ambas) si no se pasan
    explícitos, para no romper los tests existentes que solo conocían una confianza combinada."""
    from ocr.extraction import ExtractedInvoice, ExtractedTaxId, ExtractedTaxLine

    tax_ids: list = []
    if own_cif is not None:
        # El CIF propio no se puntúa (se inyecta, no se lee): confianza alta fija en ambos campos.
        tax_ids.append(
            ExtractedTaxId(
                value=own_cif, name=own_name, value_confidence="alta", name_confidence="alta"
            )
        )
    if counterparty_cif is not None:
        tax_ids.append(
            ExtractedTaxId(
                value=counterparty_cif,
                name=counterparty_name,
                value_confidence=counterparty_value_conf or counterparty_conf,
                name_confidence=counterparty_name_conf or counterparty_conf,
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
        net_amount_confidence=net_confidence or confidence,
        tax_amount=tax,
        tax_amount_confidence=tax_confidence or confidence,
        irpf_rate=irpf_rate,
        irpf_rate_confidence=irpf_rate_confidence or confidence,
        irpf_amount=irpf_amount,
        irpf_amount_confidence=irpf_amount_confidence or confidence,
        tax_lines=tax_lines,
        tax_ids=tuple(tax_ids),
        invoice_number=invoice_number,
        invoice_number_confidence=invoice_number_confidence or confidence,
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


async def run_ocr(*, tenant_id: str, company_id: str, file_id: str, extractor) -> None:
    """Invoca el job del worker directamente (import perezoso; sin arq corriendo).

    S6.7 retiró el ranking legado del fan-out del OCR principal: este helper solo necesita el
    extractor de producción inyectado.
    """
    from jobs.ocr import run_ocr as _run

    await _run(tenant_id, company_id, file_id, extractor=extractor)


async def set_ocr_experiment_enabled(dsns: dict[str, str], enabled: bool) -> None:
    """Enciende/apaga el interruptor admin-tech (S4.10) directamente en BD (superusuario).

    La fila única de `platform_settings` ya existe (la inserta la migración 0017); aquí solo se
    actualiza, sin pasar por el endpoint HTTP (ese camino ya lo prueba `test_platform_settings.py`).
    """
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "UPDATE platform_settings SET ocr_experiment_enabled = $1, "
            "ocr_auto_benchmark_enabled = $1 WHERE id = true",
            enabled,
        )
    finally:
        await conn.close()


# --- Consultas de efecto (superusuario, saltando RLS) --------------------------------------------
async def fetch_extraction(dsns: dict[str, str], *, file_id: str) -> dict | None:
    """Extracción vigente de un fichero, con `counterparty_tax_id`/`counterparty_name` descifrados
    (S5.2): dos consultas, la primera solo para conocer el `tenant_id` y derivar la clave."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        head = await conn.fetchrow(
            "SELECT tenant_id FROM ocr_extractions WHERE uploaded_file_id = $1", file_id
        )
        if head is None:
            return None
        from shared.config import get_settings  # noqa: PLC0415
        from shared.encryption import derive_tenant_encryption_key  # noqa: PLC0415

        key = derive_tenant_encryption_key(
            get_settings().db_encryption_master_key, str(head["tenant_id"])
        )
        row = await conn.fetchrow(
            "SELECT *, pgp_sym_decrypt(counterparty_tax_id, $2)::text AS __ctid, "
            "pgp_sym_decrypt(counterparty_name, $2)::text AS __cname "
            "FROM ocr_extractions WHERE uploaded_file_id = $1",
            file_id,
            key,
        )
        if row is None:
            return None
        item = dict(row)
        item["counterparty_tax_id"] = item.pop("__ctid")
        item["counterparty_name"] = item.pop("__cname")
        return item
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
    reading: dict | None = None,
) -> None:
    """Inserta directamente una fila de `ocr_ranking_entries` (superusuario), como recomienda la
    spec S4.8 §7 para probar la agregación del panel (C11) sin depender de motores reales.
    `reading` por defecto vacío (compatibilidad); pásalo para probar los "ejemplos concretos" que
    consume el panel de plataforma (2026-08-09, a petición de Julio). S6.7 C24 mantiene CIF/nombre
    fuera del JSONB y cifrados, igual que el camino real de escritura."""
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key

    reading = dict(reading or {})
    counterparty_tax_id = reading.pop("counterparty_tax_id", None)
    counterparty_name = reading.pop("counterparty_name", None)
    encryption_key = derive_tenant_encryption_key(
        get_settings().db_encryption_master_key, tenant_id
    )
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "INSERT INTO ocr_ranking_entries "
            "(tenant_id, company_id, uploaded_file_id, engine, model, reading, "
            "counterparty_tax_id, counterparty_name, score) "
            "VALUES ($1,$2,$3,$4,$5,$6::jsonb,pgp_sym_encrypt($7,$9),pgp_sym_encrypt($8,$9),$10) "
            "ON CONFLICT (uploaded_file_id, engine) DO UPDATE SET score = EXCLUDED.score, "
            "reading = EXCLUDED.reading, counterparty_tax_id = EXCLUDED.counterparty_tax_id, "
            "counterparty_name = EXCLUDED.counterparty_name",
            tenant_id,
            company_id,
            uploaded_file_id,
            engine,
            model,
            json.dumps(reading),
            counterparty_tax_id,
            counterparty_name,
            encryption_key,
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
