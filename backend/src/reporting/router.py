"""Endpoints HTTP de `reporting`: panel de facturas de la asesoría
(`GET /api/v1/reporting/invoices`, S3.1), su export a Excel
(`GET /api/v1/reporting/invoices/export`, S3.2) y la ficha agregada de empresas
(`GET /api/v1/reporting/companies`, S3.4).

Capa HTTP fina: autentica y autoriza (`tenant_admin`, portero de roles), tipa los filtros de la
query string y traduce el resultado o la excepción de dominio de `reporting.service` a la
respuesta HTTP. No contiene SQL ni reglas de negocio; el Excel se construye en `reporting.xlsx`.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from identity.authz import require_roles
from identity.dependencies import AuthContext
from reporting import service, xlsx
from tenancy.constants import Role

router = APIRouter(prefix="/reporting", tags=["reporting"])

# El panel es exclusivo de `tenant_admin` (decisión de dominio, spec S3.1 §6): el empleado (`user`)
# se queda con el historial de 7 días de S2.6.
TenantAdmin = Annotated[AuthContext, Depends(require_roles(Role.TENANT_ADMIN))]

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TaxLineOut(BaseModel):
    """Un tramo de IVA de la fila del panel."""

    iva_pct: Decimal | None
    base: Decimal | None
    cuota: Decimal | None


class InvoiceRowOut(BaseModel):
    """Una fila del panel de facturas (spec §2/§3 C8)."""

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
    tax_lines: list[TaxLineOut]
    confirmed_at: datetime
    confirmed_by: UUID
    uploaded_file_id: UUID
    uploaded_at: datetime


class PanelOut(BaseModel):
    """Respuesta de `GET /reporting/invoices`: una página del panel (spec §2)."""

    items: list[InvoiceRowOut]
    next_cursor: str | None


def _filters_from_query(
    *,
    date_from: date | None,
    date_to: date | None,
    counterparty_tax_id: str | None,
    confirmed_by: UUID | None,
    cif_status: str | None,
    company_id: UUID | None,
) -> service.PanelFilters:
    """Tipa los filtros de la query string a `PanelFilters` (compartido por panel y export)."""
    return service.PanelFilters(
        date_from=date_from,
        date_to=date_to,
        counterparty_tax_id=counterparty_tax_id,
        confirmed_by=confirmed_by,
        cif_status=cif_status,
        company_id=company_id,
    )


class CompanyRowOut(BaseModel):
    """Una fila de la ficha agregada de empresas (S3.4, spec §2/§3 C1)."""

    id: UUID
    name: str
    cif: str
    status: str
    notes: str | None
    created_at: datetime
    user_count: int
    invoice_count: int
    last_invoice_at: datetime | None


@router.get("/companies")
async def list_companies(identity: TenantAdmin) -> list[CompanyRowOut]:
    """Empresas de la asesoría con sus contadores agregados (S3.4). Ver spec S3.4."""
    rows = await service.list_companies(identity)
    return [
        CompanyRowOut(
            id=row.id,
            name=row.name,
            cif=row.cif,
            status=row.status,
            notes=row.notes,
            created_at=row.created_at,
            user_count=row.user_count,
            invoice_count=row.invoice_count,
            last_invoice_at=row.last_invoice_at,
        )
        for row in rows
    ]


@router.get("/invoices")
async def list_invoices(
    identity: TenantAdmin,
    date_from: date | None = None,
    date_to: date | None = None,
    counterparty_tax_id: str | None = None,
    confirmed_by: UUID | None = None,
    cif_status: str | None = None,
    company_id: UUID | None = None,
    cursor: str | None = None,
) -> PanelOut:
    """Facturas confirmadas de la asesoría, filtradas y paginadas (S3.1). Ver spec S3.1.

    `counterparty_tax_id` filtra por CIF EXACTO de contraparte (S5.2 C5): ya no admite texto libre
    por nombre (el nombre vive cifrado sin índice ciego desde S5.2, decisión de Julio).
    """
    filters = _filters_from_query(
        date_from=date_from,
        date_to=date_to,
        counterparty_tax_id=counterparty_tax_id,
        confirmed_by=confirmed_by,
        cif_status=cif_status,
        company_id=company_id,
    )
    try:
        page = await service.list_invoices(identity, filters, cursor)
    except service.InvalidDateRange as exc:
        raise HTTPException(
            status_code=422, detail="date_from no puede ser posterior a date_to"
        ) from exc
    except service.InvalidCursor as exc:
        raise HTTPException(status_code=422, detail="cursor inválido") from exc

    return PanelOut(
        items=[
            InvoiceRowOut(
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
                    TaxLineOut(iva_pct=t.iva_pct, base=t.base, cuota=t.cuota) for t in row.tax_lines
                ],
                confirmed_at=row.confirmed_at,
                confirmed_by=row.confirmed_by,
                uploaded_file_id=row.uploaded_file_id,
                uploaded_at=row.uploaded_at,
            )
            for row in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/invoices/export")
async def export_invoices(
    identity: TenantAdmin,
    date_from: date | None = None,
    date_to: date | None = None,
    counterparty_tax_id: str | None = None,
    confirmed_by: UUID | None = None,
    cif_status: str | None = None,
    company_id: UUID | None = None,
) -> Response:
    """Excel con todas las facturas que casan los filtros, sin paginar (S3.2). Ver spec S3.2.

    Mismos filtros que `list_invoices`; no acepta `cursor` (el export no pagina, spec §5).
    """
    filters = _filters_from_query(
        date_from=date_from,
        date_to=date_to,
        counterparty_tax_id=counterparty_tax_id,
        confirmed_by=confirmed_by,
        cif_status=cif_status,
        company_id=company_id,
    )
    try:
        items = await service.export_invoices(identity, filters)
    except service.InvalidDateRange as exc:
        raise HTTPException(
            status_code=422, detail="date_from no puede ser posterior a date_to"
        ) from exc

    # `build_export_workbook` es CPU-bound (hasta EXPORT_LIMIT filas): fuera del hilo del event
    # loop para no bloquear las peticiones de otros tenants mientras se genera (spec: solo lectura,
    # pero un export grande no debe degradar el resto del servicio).
    content = await asyncio.to_thread(xlsx.build_export_workbook, items)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="facturas.xlsx"'},
    )
