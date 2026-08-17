"""Job del worker OCR (S2.3): cablea I/O (sesión+RLS, MinIO, extractor) con el dominio puro.

`run_ocr` es la unidad de trabajo, invocable directamente (los tests la ejecutan como coroutine, sin
arq). Orden (spec S2.3 §3): fija el contexto de tenant (RLS) -> carga el fichero (vía
`invoice_intake`) y el CIF propio conocido -> descarga los bytes de MinIO -> corre los extractores
en paralelo (hoy N=1) -> reconcilia (árbitro por campo) -> analiza (contraparte, validaciones)
-> persiste la extracción y transiciona el estado del fichero, atómico en la misma transacción.

La máquina de estados y la ubicación del fichero son dominio de `invoice_intake` (no de `ocr`): el
job las invoca desde `invoice_intake.repository`. Fallo del extractor o de la descarga: el fichero
queda en `ocr_failed`, SIN fila de extracción, con el error registrado (nunca datos a medias).

Tras el resultado principal, `run_ocr` dispara la comparativa original-vs-realzada (S2.10,
`run_ocr_comparison`) en su PROPIA transacción, separada de la principal (que ya se confirmó al
llegar ahí). El ranking multi-modelo legado (S4.8) se conserva en `jobs.ocr_ranking`, pero S6.7 lo
retiró de este fan-out: el benchmark real se encola solo al CONFIRMAR, cuando ya existe una verdad
humana contra la que puntuar. El fallo de la comparativa queda contenido y jamás puede tocar el
resultado principal (spec S2.9/S2.10 C5). `run_ocr_comparison` es pública porque también la
reutiliza `jobs.ocr_backfill` (backfill retroactivo, mismo paquete `jobs`, sin duplicar esta lógica
ni invertir la dirección de dependencias jobs->ocr).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog

from companies import repository as companies_repo
from companies.service import tenant_encryption_key as company_encryption_key
from invoice_intake import repository as intake_repo
from invoice_intake import storage
from invoice_intake.constants import FileStatus
from ocr import comparison, comparison_repository, repository
from ocr.analysis import STATUS_AUTO_OK, analyze_invoice
from ocr.arbiter import reconcile
from ocr.engines.gemini_extractor import build_default_extractor
from ocr.extraction import (
    DocumentPage,
    ExtractedInvoice,
    InvoiceExtractor,
    extract_document,
    serialize_tax_lines,
)
from ocr.preprocess.enhance import (
    ENHANCED_CONTENT_TYPE,
    SUPPORTED_CONTENT_TYPES,
    enhance_invoice_image,
)
from ocr.scoring import serialize_reading
from platform_admin import settings_repository
from shared.config import get_settings
from shared.db import tenant_session

logger = structlog.get_logger(__name__)


async def run_ocr(
    tenant_id: str | UUID,
    company_id: str | UUID,
    uploaded_file_id: str | UUID,
    *,
    extractor: InvoiceExtractor | None = None,
) -> None:
    """Procesa un `uploaded_file` en `pending_ocr`: extrae, valida y decide su estado.

    `extractor` inyectable (los tests pasan un doble); si es `None`, usa el motor real por defecto
    (gemini-3-flash a JSON estructurado). Todo ocurre bajo el contexto de tenant/empresa (RLS).

    """
    tid, cid, fid = UUID(str(tenant_id)), UUID(str(company_id)), UUID(str(uploaded_file_id))
    settings = get_settings()
    # El claim se toma ANTES de construir el proveedor o descargar bytes: un mensaje duplicado no
    # puede consumir cuota. El token se exige también al persistir para cercar un lease vencido.
    async with tenant_session(tid, cid) as session:
        claim_token = await intake_repo.claim_ocr(
            session, fid, cid, lease_seconds=settings.ocr_claim_lease_seconds
        )
        if claim_token is None:
            return
        locations = await intake_repo.get_document_pages(session, fid)
        if not locations:
            await intake_repo.finish_claim(session, fid, claim_token, FileStatus.OCR_FAILED)
            logger.error("ocr.file_not_found", uploaded_file_id=str(fid))
            return

        company = await companies_repo.get_company(
            session, cid, encryption_key=company_encryption_key(settings, tid)
        )
        if company is None:
            logger.error("ocr.company_not_found", uploaded_file_id=str(fid))
            await intake_repo.finish_claim(session, fid, claim_token, FileStatus.OCR_FAILED)
            return

    try:
        # Fan-out de extractores: hoy N=1, pero se conserva la secuencia para que el árbitro por
        # campo pueda crecer con motores distintos sin reescribir el job.
        extractors: list[InvoiceExtractor] = [extractor or build_default_extractor(settings)]
        pages = [
            DocumentPage(
                content=await asyncio.to_thread(storage.get_object, location.bucket, location.key),
                content_type=location.content_type,
            )
            for location in locations
        ]
        readings = await asyncio.wait_for(
            asyncio.gather(*(extract_document(reader, pages) for reader in extractors)),
            timeout=settings.ocr_provider_timeout_seconds,
        )
        reconciled = reconcile(readings)
        analysis = analyze_invoice(reconciled, company.cif)
        file_status = (
            FileStatus.OCR_DONE if analysis.status == STATUS_AUTO_OK else FileStatus.NEEDS_REVIEW
        )
    except Exception as exc:  # noqa: BLE001 - configuración, MinIO y proveedor dejan salida segura
        await _fail_claim(tid, cid, fid, claim_token, exc)
        return

    # La extracción y el análisis ya terminaron: se abre una segunda sesión corta para confirmar el
    # resultado y la transición de estado de forma atómica.
    async with tenant_session(tid, cid) as session:
        if not await intake_repo.claim_is_current(session, fid, claim_token):
            return
        await repository.upsert_extraction(
            session,
            company_id=cid,
            uploaded_file_id=fid,
            issue_date=reconciled.issue_date,
            total_amount=reconciled.total_amount,
            net_amount=reconciled.net_amount,
            tax_amount=reconciled.tax_amount,
            invoice_number=reconciled.invoice_number,
            tax_lines=serialize_tax_lines(reconciled),
            counterparty_tax_id=analysis.counterparty_tax_id,
            counterparty_name=analysis.counterparty_name,
            own_tax_id_present=analysis.own_tax_id_present,
            confidences=analysis.confidences,
            validations=analysis.validations,
            engine=reconciled.engine,
            model=reconciled.model,
            raw=reconciled.raw,
            status=analysis.status,
            encryption_key=company_encryption_key(settings, tid),
        )
        if not await intake_repo.finish_claim(session, fid, claim_token, file_status):
            return  # el fencing evita que un worker vencido sobrescriba un claim nuevo
        logger.info(
            "ocr.extraction_done",
            uploaded_file_id=str(fid),
            status=analysis.status,
            file_status=file_status.value,
        )

    await run_ocr_comparison(
        tid,
        cid,
        fid,
        pages=pages,
        own_cif=company.cif,
        extractor=extractors[0],
        original_reading=reconciled,
    )


async def _fail_claim(
    tenant_id: UUID, company_id: UUID, file_id: UUID, claim_token: UUID, error: Exception
) -> None:
    """Marca el claim todavía vigente como fallido sin propagar contenido externo a logs."""
    async with tenant_session(tenant_id, company_id) as session:
        await intake_repo.finish_claim(session, file_id, claim_token, FileStatus.OCR_FAILED)
    logger.error(
        "ocr.processing_failed",
        uploaded_file_id=str(file_id),
        failure_type=type(error).__name__,
    )


async def run_ocr_comparison(
    tenant_id: UUID,
    company_id: UUID,
    uploaded_file_id: UUID,
    *,
    pages: list[DocumentPage],
    own_cif: str,
    extractor: InvoiceExtractor,
    original_reading: ExtractedInvoice | None = None,
) -> None:
    """Comparativa original-vs-realzada de una factura (S2.10), detrás del interruptor de S4.10.

    Transacción PROPIA: se llama tras que el resultado principal ya se confirmó (desde `run_ocr`) o
    de forma independiente sobre una factura ya procesada (desde el backfill retroactivo). Nunca
    propaga una excepción: es un experimento de coste acotado en el tiempo, no un contrato con el
    usuario, y su fallo no debe poder afectar a nada que ya haya terminado con éxito (spec C5).

    `original_reading`: si el llamador ya la tiene (camino en vivo: `run_ocr` acaba de calcularla
    para el resultado principal), se reutiliza tal cual y NO se vuelve a pedir al lector — spec §1
    dice "se lee dos veces" (la realzada + esta), no tres; repetir la lectura original sería una
    llamada de pago redundante (auditoría, hallazgo de coste). Si es `None` (backfill retroactivo,
    que procesa un fichero ya cerrado sin esa lectura en memoria), se obtiene aquí.
    """
    try:
        async with tenant_session(tenant_id, company_id) as session:
            settings = await settings_repository.get_settings(session)
            if not settings.ocr_experiment_enabled:
                return

        if not pages or any(page.content_type not in SUPPORTED_CONTENT_TYPES for page in pages):
            logger.info(
                "ocr.comparison_unsupported_document", uploaded_file_id=str(uploaded_file_id)
            )
            return

        # Coste real de CPU/memoria y llamada externa: ambos fuera de la sesión de Postgres.
        enhanced_pages = [
            DocumentPage(
                content=await asyncio.to_thread(
                    enhance_invoice_image, page.content, page.content_type
                ),
                content_type=ENHANCED_CONTENT_TYPE,
            )
            for page in pages
        ]

        resolved_original: ExtractedInvoice
        if original_reading is not None:
            resolved_original = original_reading
            enhanced_reading = await extract_document(extractor, enhanced_pages)
        else:
            resolved_original, enhanced_reading = await asyncio.gather(
                extract_document(extractor, pages), extract_document(extractor, enhanced_pages)
            )

        verdict = comparison.compare_readings(resolved_original, enhanced_reading, own_cif)
        async with tenant_session(tenant_id, company_id) as session:
            await comparison_repository.upsert_comparison_run(
                session,
                company_id=company_id,
                uploaded_file_id=uploaded_file_id,
                original_reading=serialize_reading(resolved_original, verdict.original_analysis),
                enhanced_reading=serialize_reading(enhanced_reading, verdict.enhanced_analysis),
                original_score=verdict.original_score,
                enhanced_score=verdict.enhanced_score,
                winner=verdict.winner,
                engine=resolved_original.engine,
                model=resolved_original.model,
                encryption_key=company_encryption_key(get_settings(), tenant_id),
            )
    except Exception:  # noqa: BLE001  (experimento de fondo: nunca debe tumbar al llamador)
        logger.error("ocr.comparison_failed", uploaded_file_id=str(uploaded_file_id))
