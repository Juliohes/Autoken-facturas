"""Endpoints HTTP del laboratorio OCR (S6.2, spec docs/specs/S6.2-laboratorio-ocr-admin-tech.md, +
S6.6, spec docs/specs/S6.6-laboratorio-comparacion-honesta.md, Áreas B-E): `GET /api/v1/platform/
tenants/{tenant_id}/invoices` y `GET /api/v1/platform/tenants/{tenant_id}/invoices/{file_id}/lab`.

Capa HTTP fina: autentica y autoriza (`require_admin_tech()`, S4.10, mismo patrón que
`ranking_router`/`settings_router` — un `platform_admin` sin el flag recibe 403, C1) y traduce el
resultado o la excepción de dominio de `platform_admin.lab_service` a la respuesta. Router aparte de
`tenants_router` (no el mismo fichero): ese usa `require_platform_admin()`, este exige además
`is_admin_tech`, un portero distinto sobre el mismo prefijo `/platform/tenants`.

El panel de facturas de cada tenant (`reporting`/`invoicing`) NO cambia por esta tarea (spec C3):
cero imports ni cambios en esos routers.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from identity.authz import require_admin_tech
from identity.dependencies import AdminTechAuthContext
from invoicing.service import ReviewData
from platform_admin import lab_service, service
from reporting.repository import InvoiceRow

router = APIRouter(prefix="/platform/tenants", tags=["platform"])

_BINARY_IMAGE_CONTENT: dict[str, Any] = {
    "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
    "image/png": {"schema": {"type": "string", "format": "binary"}},
}
_BINARY_DOCUMENT_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Bytes binarios del documento original autorizado.",
        "content": {
            **_BINARY_IMAGE_CONTENT,
            "application/pdf": {"schema": {"type": "string", "format": "binary"}},
        },
    }
}

AdminTech = Annotated[AdminTechAuthContext, Depends(require_admin_tech())]


class LabTaxLineOut(BaseModel):
    """Un tramo de IVA de una fila del listado (mismo shape que `reporting.router.TaxLineOut`)."""

    iva_pct: Decimal | None
    base: Decimal | None
    cuota: Decimal | None


class LabInvoiceRowOut(BaseModel):
    """Una fila del listado de facturas confirmadas de un tenant (S6.2, spec C2): mismas columnas
    que ya muestra `InvoicesPanel` del tenant (S3.1), aquí en solo lectura desde plataforma."""

    id: UUID
    company_name: str
    company_cif: str
    issue_date: date | None
    direction: str
    counterparty_tax_id: str | None
    counterparty_name: str | None
    counterparty_cif_status: str
    net_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    irpf_amount: Decimal | None
    tax_lines: list[LabTaxLineOut]
    confirmed_at: datetime
    confirmed_by: UUID
    uploaded_file_id: UUID
    uploaded_at: datetime


def _row_to_out(row: InvoiceRow) -> LabInvoiceRowOut:
    return LabInvoiceRowOut(
        id=row.id,
        company_name=row.company_name,
        company_cif=row.company_cif,
        issue_date=row.issue_date,
        direction=row.direction,
        counterparty_tax_id=row.counterparty_tax_id,
        counterparty_name=row.counterparty_name,
        counterparty_cif_status=row.counterparty_cif_status,
        net_amount=row.net_amount,
        tax_amount=row.tax_amount,
        total_amount=row.total_amount,
        irpf_amount=row.irpf_amount,
        tax_lines=[
            LabTaxLineOut(iva_pct=line.iva_pct, base=line.base, cuota=line.cuota)
            for line in row.tax_lines
        ],
        confirmed_at=row.confirmed_at,
        confirmed_by=row.confirmed_by,
        uploaded_file_id=row.uploaded_file_id,
        uploaded_at=row.uploaded_at,
    )


@router.get("/{tenant_id}/invoices")
async def list_tenant_invoices(identity: AdminTech, tenant_id: UUID) -> list[LabInvoiceRowOut]:
    """Facturas confirmadas del tenant elegido desde el laboratorio (S6.2, spec C2). Id
    inexistente -> 404 explícito (spec C4)."""
    try:
        rows = await lab_service.list_tenant_invoices(identity.session, tenant_id)
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    return [_row_to_out(row) for row in rows]


def _reading_1_out(reading_1: lab_service.Reading1 | None) -> dict[str, object] | None:
    if reading_1 is None:
        return None
    return {"raw": reading_1.raw, "engine": reading_1.engine, "model": reading_1.model}


def _reading_2_out(reading_2: ReviewData | None) -> dict[str, object] | None:
    """Mismo shape que ya expone `GET /uploads/{file_id}/review` (S2.4)."""
    if reading_2 is None:
        return None
    return {
        "fields": reading_2.fields,
        "confidences": reading_2.confidences,
        "counterparty_verdict": reading_2.counterparty_verdict,
        "own": reading_2.own,
        "warnings": reading_2.warnings,
        "blocking_reasons": reading_2.blocking_reasons,
    }


def _reading_3_out(reading_3: lab_service.Reading3) -> dict[str, object]:
    """Tabla unificada de comparación honesta (S6.6, spec C4-C11): sustituye a `corrections`/
    `has_corrections` de S6.2 por un badge por cada uno de los 7 campos escalares más la fila
    manual de tramos de IVA."""
    return {
        "invoice": reading_3.invoice,
        "field_comparison": [
            {
                "field": row.field,
                "column_2": row.column_2,
                "column_3": row.column_3,
                "match": row.match,
            }
            for row in reading_3.field_comparison
        ],
        "tax_lines_comparison": {
            "column_2": reading_3.tax_lines_comparison.column_2,
            "column_3": reading_3.tax_lines_comparison.column_3,
            "match": reading_3.tax_lines_comparison.match,
        },
    }


@router.get("/{tenant_id}/invoices/{file_id}/image", responses=_BINARY_DOCUMENT_RESPONSE)
async def get_invoice_image(identity: AdminTech, tenant_id: UUID, file_id: UUID) -> Response:
    """Foto original de una factura del tenant elegido, para el botón "Ver" del laboratorio (spec
    C2). Mismo patrón de 404 que el resto de este router (C4/C5)."""
    try:
        content, content_type = await lab_service.get_invoice_image(
            identity.session, tenant_id, file_id
        )
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    except lab_service.InvoiceNotFoundForLab as exc:
        raise HTTPException(status_code=404, detail="Factura no encontrada") from exc
    return Response(content=content, media_type=content_type)


@router.get("/{tenant_id}/invoices/{file_id}/lab")
async def get_invoice_lab(identity: AdminTech, tenant_id: UUID, file_id: UUID) -> dict[str, object]:
    """Las 3 lecturas + comparativa de modelos de una factura del tenant elegido (S6.2, spec
    C6-C13). Tenant inexistente -> 404 (spec C4); fichero de otro tenant o inexistente -> 404 (spec
    C5)."""
    try:
        result = await lab_service.get_invoice_lab(identity.session, tenant_id, file_id)
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    except lab_service.InvoiceNotFoundForLab as exc:
        raise HTTPException(status_code=404, detail="Factura no encontrada") from exc
    return {
        "reading_1": _reading_1_out(result.reading_1),
        "reading_2": _reading_2_out(result.reading_2),
        "reading_3": _reading_3_out(result.reading_3),
        "ranking": [
            {
                "variant": row.variant,
                "engine": row.engine,
                "field_results": row.field_results,
                "tax_lines_matched": row.tax_lines_matched,
            }
            for row in result.ranking
        ],
        "ranking_available": result.ranking_available,
    }
