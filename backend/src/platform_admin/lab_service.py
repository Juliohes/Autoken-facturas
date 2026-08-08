"""Lógica de dominio del laboratorio OCR (S6.2, spec docs/specs/S6.2-laboratorio-ocr-admin-tech.md):
diagnóstico por factura, solo accesible desde el panel de plataforma (`platform_admin` +
`is_admin_tech`, S4.10).

Mismo patrón que `platform_admin.service.export_tenant` (S4.7, spec §0 de esta tarea): la sesión de
la petición es de plataforma (`platform_session`, sin `app.tenant_id` fijado, la usa un
`platform_admin`); para leer los datos de UN tenant concreto, el propio servicio valida que existe
(`repository.list_tenants`) y abre su PROPIA `tenant_session(tenant_id)`, bajo cuya RLS de dos
niveles ya construida se apoya todo lo demás (nunca una función `SECURITY DEFINER` de lectura por
tabla nueva). Solo lectura: no persiste nada, no reabre la posibilidad de confirmar ni editar.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from invoice_intake import repository as intake_repository
from invoice_intake import storage as intake_storage
from invoicing import repository as invoicing_repository
from invoicing import service as invoicing_service
from ocr import ranking_repository
from ocr import repository as ocr_repository
from platform_admin import repository as platform_repository
from platform_admin import service as platform_service
from reporting import repository as reporting_repository
from shared.config import get_settings
from shared.db import tenant_session
from shared.encryption import tenant_encryption_key
from tenancy.constants import Role

__all__ = [
    "InvoiceNotFoundForLab",
    "LabResult",
    "Reading1",
    "Reading3",
    "Reading3Correction",
    "get_invoice_image",
    "get_invoice_lab",
    "list_tenant_invoices",
]


class InvoiceNotFoundForLab(Exception):
    """El fichero no tiene ninguna factura confirmada visible en el tenant elegido (S6.2, spec C5).

    Cubre a la vez "no existe ese fichero" y "existe pero es de OTRO tenant": la `tenant_session`
    abierta por `get_invoice_lab` ya hace invisible cualquier fila de otro tenant vía la RLS de dos
    niveles ya construida, sin ninguna comprobación manual adicional (-> 404 "Factura no
    encontrada", mismo mensaje que ya usa `invoicing.router` para `InvoiceNotVisible`, S3.3).
    """


@dataclass(frozen=True)
class Reading1:
    """Lectura 1 (IA cruda, spec C6/C7): la respuesta del proveedor tal cual, sin ningún procesado
    de dominio, más qué motor la produjo."""

    raw: dict[str, Any]
    engine: str
    model: str


@dataclass(frozen=True)
class Reading3Correction:
    """Una corrección humana de la Lectura 3 (spec C10): campo, valor de la IA, valor humano."""

    field: str
    ai_value: str | None
    human_value: str | None


@dataclass(frozen=True)
class Reading3:
    """Lectura 3 (guardado final, spec C10/C11): la factura confirmada + el diff de correcciones.

    `has_corrections` explícito (no una lista vacía muda, spec C11): distingue "sin correcciones"
    de un futuro error de carga que dejara la lista vacía por otro motivo.
    """

    invoice: dict[str, object]
    corrections: list[Reading3Correction]
    has_corrections: bool


@dataclass(frozen=True)
class LabResult:
    """Las 3 lecturas + la comparativa de modelos de una factura (S6.2).

    `reading_1`/`reading_2` son `None` solo en el caso teórico de una extracción sin fila
    persistida (spec §5: "fuera de alcance, no se contempla un fallback especial" — `raw` es
    `NOT NULL` desde S2.3, así que una factura confirmada siempre debería tener extracción).
    `ranking_available` es `False` cuando el experimento (S4.10) no estaba encendido al procesar
    esta factura en concreto (spec C13): no es un error, se dice explícitamente.
    """

    reading_1: Reading1 | None
    reading_2: invoicing_service.ReviewData | None
    reading_3: Reading3
    ranking: list[ranking_repository.RankingEntry]
    ranking_available: bool


# Rol usado para recalcular `blocking_reasons` en la Lectura 2 (spec C8): el laboratorio no conoce
# qué rol tenía el usuario que confirmó en su día, y la spec pide mostrar el diagnóstico con las
# reglas ACTUALES, no reconstruir la sesión original (C8, "puede diferir... es correcto y
# esperado"). Se usa `USER` (el rol más restrictivo) para que el diagnóstico muestre SIEMPRE el
# motivo de bloqueo más completo posible (p. ej. `own_tax_id_missing`), en vez de que `TENANT_ADMIN`
# lo oculte silenciosamente por su exención — más útil para diagnosticar qué falló, spec §1.
_LAB_ROLE = Role.USER.value


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _num(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _invoice_dict(invoice: invoicing_repository.InvoiceRecord) -> dict[str, object]:
    """Proyección JSON-serializable de `InvoiceRecord` para la Lectura 3 (spec C10): importes y
    fecha como texto, igual criterio que `invoicing.service.ReviewData.fields`."""
    return {
        "id": str(invoice.id),
        "company_id": str(invoice.company_id),
        "uploaded_file_id": str(invoice.uploaded_file_id),
        "direction": invoice.direction,
        "issue_date": _iso(invoice.issue_date),
        "invoice_number": invoice.invoice_number,
        "counterparty_tax_id": invoice.counterparty_tax_id,
        "counterparty_name": invoice.counterparty_name,
        "counterparty_cif_status": invoice.counterparty_cif_status,
        "net_amount": _num(invoice.net_amount),
        "tax_amount": _num(invoice.tax_amount),
        "total_amount": _num(invoice.total_amount),
        "irpf_amount": _num(invoice.irpf_amount),
        "is_test": invoice.is_test,
        "balance_ok": invoice.balance_ok,
        "status": invoice.status,
        "confirmed_by": str(invoice.confirmed_by),
        "confirmed_at": invoice.confirmed_at.isoformat(),
        "tax_lines": [
            {"iva_pct": _num(iva_pct), "base": _num(base), "cuota": _num(cuota)}
            for iva_pct, base, cuota in invoice.tax_lines
        ],
    }


async def _existing_tenant_or_raise(session: AsyncSession, tenant_id: UUID) -> None:
    """Valida que el tenant existe (mismo criterio que `platform_admin.service.export_tenant`,
    S4.7): -> `platform_service.TenantNotFound` si no (spec C4)."""
    tenants = await platform_repository.list_tenants(session)
    if not any(t.id == tenant_id for t in tenants):
        raise platform_service.TenantNotFound()


async def list_tenant_invoices(
    session: AsyncSession, tenant_id: UUID
) -> list[reporting_repository.InvoiceRow]:
    """Facturas confirmadas del tenant elegido (S6.2, spec C2): mismas columnas que `InvoicesPanel`
    del tenant (S3.1), en solo lectura. Id inexistente -> `platform_service.TenantNotFound`.

    `list_all` (no `list_invoices`, el del panel paginado): el laboratorio no pagina, así que
    reutilizar `list_invoices` (piensa `PAGE_SIZE + 1` filas para que el LLAMANTE recorte a una
    página) habría truncado en silencio cualquier tenant con más de 50 facturas confirmadas, sin
    ningún aviso ni forma de ver el resto (hallazgo real de auditoría) — mismo criterio de "nunca
    se trunca en silencio" que ya usa `list_for_export`.
    """
    await _existing_tenant_or_raise(session, tenant_id)
    encryption_key = tenant_encryption_key(get_settings(), tenant_id)
    async with tenant_session(tenant_id) as ts:
        return await reporting_repository.list_all(
            ts,
            filters=reporting_repository.Filters(),
            encryption_key=encryption_key,
        )


async def get_invoice_lab(session: AsyncSession, tenant_id: UUID, file_id: UUID) -> LabResult:
    """Las 3 lecturas + comparativa de una factura del tenant elegido (S6.2, spec C6-C13).

    Id de tenant inexistente -> `platform_service.TenantNotFound` (spec C4). Fichero inexistente o
    de OTRO tenant -> `InvoiceNotFoundForLab` (spec C5): la comprobación real es que
    `get_invoice_by_uploaded_file_id` no encuentre ninguna fila DENTRO de la `tenant_session` del
    tenant elegido, la RLS de dos niveles ya construida hace el resto.
    """
    await _existing_tenant_or_raise(session, tenant_id)
    encryption_key = tenant_encryption_key(get_settings(), tenant_id)

    async with tenant_session(tenant_id) as ts:
        invoice = await invoicing_repository.get_invoice_by_uploaded_file_id(
            ts, file_id, encryption_key=encryption_key
        )
        if invoice is None:
            raise InvoiceNotFoundForLab()

        # Extracción sin `raw` (caso teórico, `raw` es `NOT NULL` desde S2.3): fuera de alcance
        # (spec §5), no se contempla un fallback especial más allá de dejar las lecturas 1/2 en
        # `None` en vez de fallar con un error opaco.
        extraction = await ocr_repository.get_extraction(ts, file_id, encryption_key=encryption_key)
        reading_1 = (
            Reading1(raw=extraction.raw, engine=extraction.engine, model=extraction.model)
            if extraction is not None
            else None
        )
        reading_2 = (
            await invoicing_service.build_review_data(
                ts, tenant_id, invoice.company_id, extraction, _LAB_ROLE
            )
            if extraction is not None
            else None
        )

        corrections = await invoicing_repository.list_corrections(ts, file_id)
        reading_3 = Reading3(
            invoice=_invoice_dict(invoice),
            corrections=[
                Reading3Correction(
                    field=correction.field,
                    ai_value=correction.ai_value,
                    human_value=correction.human_value,
                )
                for correction in corrections
            ],
            has_corrections=bool(corrections),
        )

        ranking = await ranking_repository.list_ranking_entries(ts, file_id)

    return LabResult(
        reading_1=reading_1,
        reading_2=reading_2,
        reading_3=reading_3,
        ranking=ranking,
        ranking_available=bool(ranking),
    )


async def get_invoice_image(
    session: AsyncSession, tenant_id: UUID, file_id: UUID
) -> tuple[bytes, str]:
    """Bytes + MIME real de la foto original de una factura, para el botón "Ver" del laboratorio
    (spec C2, "Ver (la foto) / Laboratorio (las 3 lecturas), por fila").

    A diferencia de `invoice_intake.router::download_image` (el "Ver" del panel tenant-scoped, S2.1/
    2026-08-01/02), aquí NO hay una identidad de tenant con `actor_user_id`/`actor_role` de la que
    partir (`AdminTechAuthContext` es de plataforma) — el admin-tech ve cualquier fichero del tenant
    que ya validó, sin la restricción "por-usuario" de S3.9/02-08-2026 (esa restricción protege a un
    `user` de otro `user`, no aplica a un diagnóstico de plataforma). Tenant inexistente ->
    `platform_service.TenantNotFound` (C4); fichero de otro tenant/inexistente -> el mismo
    `InvoiceNotFoundForLab` que ya usa `get_invoice_lab` (C5) — la RLS de la `tenant_session` hace
    invisible cualquier fila ajena, sin comprobación manual adicional.
    """
    await _existing_tenant_or_raise(session, tenant_id)
    async with tenant_session(tenant_id) as ts:
        invoice = await invoicing_repository.get_invoice_by_uploaded_file_id(
            ts, file_id, encryption_key=tenant_encryption_key(get_settings(), tenant_id)
        )
        if invoice is None:
            raise InvoiceNotFoundForLab()
        location = await intake_repository.get_file_location(ts, file_id)
        if location is None:
            raise InvoiceNotFoundForLab()

    content = await asyncio.to_thread(intake_storage.get_object, location.bucket, location.key)
    return content, location.content_type
