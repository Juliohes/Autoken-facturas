"""Job del worker del benchmark real de variante x motor (S6.7, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C1): cablea I/O (sesión+RLS, MinIO, motores
reales, verdad confirmada) con el motor de dominio `ocr.benchmark.run_benchmark`.

Único punto de producción legítimo que construye los 6 motores reales desde `.env`
(`ocr.ranking_engines.build_named_ranking_extractors`) -- mismo criterio ya auditado que
`jobs.ocr.run_ocr`/`jobs.ocr_ranking.run_ocr_ranking` (ver sus docstrings para el incidente real de
coste de S4.8 que este patrón evita: un test que llama a `run_ocr_benchmark_task` sin inyectar sus
propios extractores SÍ dispara llamadas de pago reales si el entorno tiene credenciales configuradas
-- `ocr.benchmark.run_benchmark` en sí NUNCA construye motores reales por su cuenta).

Este job resuelve TAMBIÉN el interruptor (`platform_settings.ocr_experiment_enabled`) y el CIF
propio de la empresa (2026-08-11, S6.7 auditoría, hallazgo de arquitectura): `ocr.benchmark` ya no
importa `companies`/`platform_admin` (invertía la dirección de dependencias del monorepo, ver su
docstring) -- los recibe ya resueltos. Si el interruptor está apagado, el job sale de inmediato, SIN
descargar de MinIO ni construir los 6 extractores reales (evita el mismo coste que `run_benchmark`
ya evitaba, pero ahora también el de la descarga y la construcción de motores).

Sesión CORTA (mismo patrón que `jobs.ocr_ranking_backfill._process_candidate`) solo para leer el
interruptor, la verdad confirmada (la factura, ya persistida por `invoicing.service.confirm`), el
CIF propio de la empresa y la ubicación del fichero; se cierra ANTES de descargar de MinIO y de
llamar a los motores reales (I/O pesado y llamadas de pago fuera de una transacción abierta).

Toda la tarea es un experimento de fondo (best-effort, detrás del interruptor): un fallo aquí
(fichero borrado de MinIO, factura aún no visible por la ventana de carrera de
encolar-antes-de-comprometer, ya tolerada en el proyecto para el job OCR principal) se registra y se
abandona, nunca revienta el worker ni bloquea nada que ya haya terminado con éxito -- mismo criterio
que el resto de experimentos de S2.9/S2.10/S4.8.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog

from companies import repository as companies_repo
from invoice_intake import repository as intake_repo
from invoice_intake import storage
from invoicing import repository as invoicing_repo
from ocr.benchmark import run_benchmark
from ocr.ranking_engines import build_named_ranking_extractors
from platform_admin import settings_repository
from shared.config import get_settings
from shared.db import tenant_session
from shared.encryption import tenant_encryption_key

logger = structlog.get_logger(__name__)

__all__ = ["run_ocr_benchmark_task"]


def _fmt_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _fmt_amount(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _build_truth(invoice: invoicing_repo.InvoiceRecord) -> dict[str, Any]:
    """Proyección de la factura confirmada al vocabulario que espera `ocr.benchmark_scoring` (spec
    §2): mismo criterio de formateo (texto, no `Decimal`/`date`) que el resto del laboratorio
    (`platform_admin.lab_service._invoice_dict`); tramos de IVA con la clave canónica del dominio
    `iva_pct` (no `rate`, ver `ocr.benchmark._build_reading` para el porqué de esa distinción)."""
    return {
        "counterparty_tax_id": invoice.counterparty_tax_id,
        "counterparty_name": invoice.counterparty_name,
        "invoice_number": invoice.invoice_number,
        "issue_date": _fmt_date(invoice.issue_date),
        "total_amount": _fmt_amount(invoice.total_amount),
        "net_amount": _fmt_amount(invoice.net_amount),
        "tax_amount": _fmt_amount(invoice.tax_amount),
        "tax_lines": [
            {
                "iva_pct": _fmt_amount(iva_pct),
                "base": _fmt_amount(base),
                "cuota": _fmt_amount(cuota),
            }
            for iva_pct, base, cuota in invoice.tax_lines
        ],
    }


async def run_ocr_benchmark_task(
    ctx: dict[str, Any], tenant_id: str, company_id: str, uploaded_file_id: str
) -> None:
    """Task de arq: adapta la firma `(ctx, *args)` de arq al motor de dominio `ocr.benchmark.
    run_benchmark`. `ctx` no se usa (el job abre su propia sesión con contexto tenant), igual que
    `jobs.worker.run_ocr_task`. Nunca propaga una excepción (experimento de fondo)."""
    tid, cid, fid = UUID(tenant_id), UUID(company_id), UUID(uploaded_file_id)
    try:
        settings = get_settings()
        encryption_key = tenant_encryption_key(settings, tid)
        async with tenant_session(tid, cid) as session:
            settings_row = await settings_repository.get_settings(session)
            if not settings_row.ocr_experiment_enabled:
                # Interruptor apagado (C1, spec §4): coste cero, sin descargar de MinIO ni
                # construir ningún motor real.
                return

            invoice = await invoicing_repo.get_invoice_by_uploaded_file_id(
                session, fid, encryption_key=encryption_key
            )
            if invoice is None:
                # Ventana de carrera ya tolerada en el proyecto (encolar dentro de `confirm` antes
                # de que su transacción se comprometa del todo, mismo guardarraíl que
                # `jobs.ocr.run_ocr` ante un fichero aún no visible): se registra y se abandona.
                logger.error(
                    "ocr_benchmark.invoice_not_found",
                    uploaded_file_id=str(fid),
                    tenant_id=str(tid),
                )
                return
            location = await intake_repo.get_file_location(session, fid)
            if location is None:
                logger.error(
                    "ocr_benchmark.file_not_found", uploaded_file_id=str(fid), tenant_id=str(tid)
                )
                return
            company = await companies_repo.get_company(session, cid, encryption_key=encryption_key)
            if company is None:
                logger.error(
                    "ocr_benchmark.company_not_found",
                    company_id=str(cid),
                    uploaded_file_id=str(fid),
                )
                return
            truth = _build_truth(invoice)

        content = await asyncio.to_thread(storage.get_object, location.bucket, location.key)
        extractors = build_named_ranking_extractors(settings)
        await run_benchmark(
            tid,
            cid,
            fid,
            content=content,
            content_type=location.content_type,
            truth=truth,
            own_cif=company.cif,
            ocr_experiment_enabled=True,
            extractors=extractors,
        )
    except Exception as exc:  # noqa: BLE001  (experimento de fondo: nunca debe tumbar al worker)
        logger.error("ocr_benchmark.task_failed", uploaded_file_id=str(fid), error=str(exc))
