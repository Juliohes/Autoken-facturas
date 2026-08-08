"""Job del worker OCR (S2.3): cablea I/O (sesión+RLS, MinIO, extractor) con el dominio puro.

`run_ocr` es la unidad de trabajo, invocable directamente (los tests la ejecutan como coroutine, sin
arq). Orden (spec S2.3 §3): fija el contexto de tenant (RLS) -> carga el fichero (vía
`invoice_intake`) y el CIF propio conocido -> descarga los bytes de MinIO -> corre los extractores
en paralelo (hoy N=1) -> reconcilia (árbitro por campo) -> analiza (contraparte, validaciones)
-> persiste la extracción y transiciona el estado del fichero, atómico en la misma transacción.

La máquina de estados y la ubicación del fichero son dominio de `invoice_intake` (no de `ocr`): el
job las invoca desde `invoice_intake.repository`. Fallo del extractor o de la descarga: el fichero
queda en `ocr_failed`, SIN fila de extracción, con el error registrado (nunca datos a medias).

Tras el resultado principal, `run_ocr` dispara dos experimentos independientes, cada uno en su
PROPIA transacción, separada de la principal (que ya se confirmó al llegar ahí): la comparativa
original-vs-realzada (S2.10, `run_ocr_comparison`) y el ranking multi-modelo (S4.8,
`jobs.ocr_ranking.run_ocr_ranking`). Cualquier fallo de cualquiera de los dos (interruptor, motor,
persistencia) queda contenido y jamás puede tocar el resultado principal (spec S2.9/S2.10 C5,
generalizado a S4.8). `run_ocr_comparison` es pública (no `_privada`) porque también la reutiliza
`jobs.ocr_backfill` (backfill retroactivo, mismo paquete `jobs`, sin duplicar esta lógica ni
invertir la dirección de dependencias jobs->ocr).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from uuid import UUID

import structlog

from companies import repository as companies_repo
from companies.service import tenant_encryption_key as company_encryption_key
from invoice_intake import repository as intake_repo
from invoice_intake import storage
from invoice_intake.constants import FileStatus
from jobs.ocr_ranking import run_ocr_ranking
from ocr import comparison, comparison_repository, repository
from ocr.analysis import STATUS_AUTO_OK, analyze_invoice
from ocr.arbiter import reconcile
from ocr.engines.gemini_extractor import build_default_extractor
from ocr.extraction import (
    ExtractedInvoice,
    InvoiceExtractionError,
    InvoiceExtractor,
    serialize_tax_lines,
)
from ocr.preprocess.enhance import (
    ENHANCED_CONTENT_TYPE,
    SUPPORTED_CONTENT_TYPES,
    enhance_invoice_image,
)
from ocr.ranking_engines import build_additional_ranking_extractors
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
    ranking_extractors: list[InvoiceExtractor] | None = None,
) -> None:
    """Procesa un `uploaded_file` en `pending_ocr`: extrae, valida y decide su estado.

    `extractor` inyectable (los tests pasan un doble); si es `None`, usa el motor real por defecto
    (gemini-3-flash a JSON estructurado). Todo ocurre bajo el contexto de tenant/empresa (RLS).

    `ranking_extractors` (S4.8) inyectable IGUAL que `extractor`, pero representa solo los motores
    ADICIONALES al por defecto (Claude, gpt-5.1, Azure DocIntel, Mistral, Gemini Pro): la lectura
    del motor por defecto ya se calculó arriba como `reconciled` y se reutiliza tal cual para el
    ranking (`default_reading`), en vez de pedírsela otra vez a Gemini Flash — pedirla dos veces
    pagaría esa llamada el doble por factura, el mismo bug de coste duplicado que ya se corrigió en
    S2.10 (auditoría, hallazgo crítico de S4.8). Los tests SIEMPRE deben pasar una lista explícita
    (aunque sea vacía) en vez de dejarlo en `None` cuando activen el interruptor: dejado en `None`,
    aquí (el único punto de producción legítimo para ese fallback) se construyen los 5 motores
    adicionales reales desde la config (incidente real durante el desarrollo de S4.8: un test con
    el interruptor encendido llamó a `run_ocr` sin pasar `ranking_extractors` y disparó llamadas de
    pago reales a los 6 proveedores, porque este entorno de desarrollo SÍ tiene credenciales reales
    configuradas en el `.env`; `run_ocr_ranking` ya no tiene ningún fallback propio, ver su
    docstring).
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

        company = await companies_repo.get_company(
            session, cid, encryption_key=company_encryption_key(get_settings(), tid)
        )
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
            encryption_key=company_encryption_key(get_settings(), tid),
        )
        await intake_repo.transition_status(session, fid, file_status)
        logger.info(
            "ocr.extraction_done",
            uploaded_file_id=str(fid),
            status=analysis.status,
            file_status=file_status.value,
        )

    # S2.10 (original-vs-realzada) y S4.8 (ranking multi-modelo) son experimentos independientes
    # entre sí (tablas y ejes de comparación distintos, ver docstrings de cada uno) que comparten el
    # mismo interruptor: se lanzan en paralelo, cada uno con su propia transacción y su propio
    # blindaje ante fallos (ninguno de los dos puede afectar al resultado principal ya confirmado).
    await asyncio.gather(
        run_ocr_comparison(
            tid,
            cid,
            fid,
            content=content,
            content_type=location.content_type,
            own_cif=company.cif,
            extractor=extractors[0],
            original_reading=reconciled,
        ),
        run_ocr_ranking(
            tid,
            cid,
            fid,
            content=content,
            content_type=location.content_type,
            own_cif=company.cif,
            extractors=(
                ranking_extractors
                if ranking_extractors is not None
                else build_additional_ranking_extractors(get_settings())
            ),
            default_reading=reconciled,
        ),
    )


async def run_ocr_comparison(
    tenant_id: UUID,
    company_id: UUID,
    uploaded_file_id: UUID,
    *,
    content: bytes,
    content_type: str,
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
            if content_type not in SUPPORTED_CONTENT_TYPES:
                return  # PDF u otro formato no fotografiable: fuera de alcance de dominio (C3).

            # Coste real de CPU/memoria (decodificar + 3 realces + codificar): fuera del event loop,
            # igual que ya se hace con la descarga de MinIO (auditoría, hallazgo de bloqueo).
            enhanced_bytes = await asyncio.to_thread(enhance_invoice_image, content, content_type)

            resolved_original: ExtractedInvoice
            if original_reading is not None:
                resolved_original = original_reading
                enhanced_reading = await extractor.extract(enhanced_bytes, ENHANCED_CONTENT_TYPE)
            else:
                resolved_original, enhanced_reading = await asyncio.gather(
                    extractor.extract(content, content_type),
                    extractor.extract(enhanced_bytes, ENHANCED_CONTENT_TYPE),
                )

            verdict = comparison.compare_readings(resolved_original, enhanced_reading, own_cif)
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
            )
    except Exception as exc:  # noqa: BLE001  (experimento de fondo: nunca debe tumbar al llamador)
        logger.error(
            "ocr.comparison_failed", uploaded_file_id=str(uploaded_file_id), error=str(exc)
        )
