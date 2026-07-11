"""Job del worker OCR (S2.3): cablea I/O (sesión+RLS, MinIO, extractor) con el dominio puro.

`run_ocr` es la unidad de trabajo, invocable directamente (los tests la ejecutan como coroutine, sin
arq). Orden (spec S2.3 §3): fija el contexto de tenant (RLS) -> carga el fichero (vía
`invoice_intake`) y el CIF propio conocido -> descarga los bytes de MinIO -> corre los extractores
en paralelo (hoy N=1) -> reconcilia (árbitro por campo) -> analiza (contraparte, validaciones)
-> persiste la extracción y transiciona el estado del fichero, atómico en la misma transacción.

La máquina de estados y la ubicación del fichero son dominio de `invoice_intake` (no de `ocr`): el
job las invoca desde `invoice_intake.repository`. Fallo del extractor o de la descarga: el fichero
queda en `ocr_failed`, SIN fila de extracción, con el error registrado (nunca datos a medias).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from uuid import UUID

import structlog

from companies import repository as companies_repo
from invoice_intake import repository as intake_repo
from invoice_intake import storage
from invoice_intake.constants import FileStatus
from ocr import repository
from ocr.analysis import STATUS_AUTO_OK, analyze_invoice
from ocr.arbiter import reconcile
from ocr.engines.gemini_extractor import build_default_extractor
from ocr.extraction import ExtractedInvoice, InvoiceExtractionError, InvoiceExtractor
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
    # Fan-out de extractores: hoy N=1 (una sola lectura), pero modelado como secuencia para que el
    # árbitro por campo reconcilie N>1 sin reescribir el job (ADR-0016). NUNCA se repite el MISMO
    # motor: la secuencia crecerá con motores DISTINTOS cuando el CIF de contraparte lo exija.
    extractors: Sequence[InvoiceExtractor] = [extractor or build_default_extractor(get_settings())]

    async with tenant_session(tid, cid) as session:
        location = await intake_repo.get_file_location(session, fid)
        if location is None:
            # Sin fila visible no hay estado que transicionar; se registra y se abandona.
            logger.error("ocr.file_not_found", uploaded_file_id=str(fid), tenant_id=str(tid))
            return

        company = await companies_repo.get_company(session, cid)
        if company is None:
            logger.error("ocr.company_not_found", company_id=str(cid), tenant_id=str(tid))
            await intake_repo.transition_status(session, fid, FileStatus.OCR_FAILED)
            return

        try:
            content = await asyncio.to_thread(storage.get_object, location.bucket, location.key)
            readings = await asyncio.gather(
                *(reader.extract(content, location.content_type) for reader in extractors)
            )
        except (InvoiceExtractionError, storage.StorageUnavailable) as exc:
            logger.error("ocr.extraction_failed", uploaded_file_id=str(fid), error=str(exc))
            await intake_repo.transition_status(session, fid, FileStatus.OCR_FAILED)
            return

        reconciled = reconcile(readings)
        analysis = analyze_invoice(reconciled, company.cif)
        file_status = (
            FileStatus.OCR_DONE if analysis.status == STATUS_AUTO_OK else FileStatus.NEEDS_REVIEW
        )

        await repository.upsert_extraction(
            session,
            company_id=cid,
            uploaded_file_id=fid,
            issue_date=reconciled.issue_date,
            total_amount=reconciled.total_amount,
            net_amount=reconciled.net_amount,
            tax_amount=reconciled.tax_amount,
            tax_lines=_serialize_tax_lines(reconciled),
            counterparty_tax_id=analysis.counterparty_tax_id,
            counterparty_name=analysis.counterparty_name,
            own_tax_id_present=analysis.own_tax_id_present,
            confidences=analysis.confidences,
            validations=analysis.validations,
            engine=reconciled.engine,
            model=reconciled.model,
            raw=reconciled.raw,
            status=analysis.status,
        )
        await intake_repo.transition_status(session, fid, file_status)
        logger.info(
            "ocr.extraction_done",
            uploaded_file_id=str(fid),
            status=analysis.status,
            file_status=file_status.value,
        )


def _serialize_tax_lines(invoice: ExtractedInvoice) -> list[dict[str, str]]:
    """Tramos a JSON-friendly: los importes como `str` para no perder precisión decimal en jsonb."""
    return [
        {"base": str(line.base), "rate": str(line.rate), "cuota": str(line.cuota)}
        for line in invoice.tax_lines
    ]
