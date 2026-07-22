"""Endpoint HTTP del panel de facturas de la asesoría (S3.1): `GET /api/v1/reporting/invoices`.

Capa HTTP fina: autentica y autoriza (`tenant_admin`, portero de roles), tipa los filtros de la
query string y traduce el resultado o la excepción de dominio de `reporting.service` a la
respuesta HTTP. No contiene SQL ni reglas de negocio.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from identity.authz import require_roles
from identity.dependencies import AuthContext
from reporting import service
from tenancy.constants import Role

router = APIRouter(prefix="/reporting", tags=["reporting"])

# El panel es exclusivo de `tenant_admin` (decisión de dominio, spec S3.1 §6): el empleado (`user`)
# se queda con el historial de 7 días de S2.6.
TenantAdmin = Annotated[AuthContext, Depends(require_roles(Role.TENANT_ADMIN))]


class TaxLineOut(BaseModel):
    """Un tramo de IVA de la fila del panel."""

    iva_pct: Decimal | None
    base: Decimal | None
    cuota: Decimal | None


class InvoiceRowOut(BaseModel):
    """Una fila del panel de facturas (spec §2/§3 C8)."""

    id: UUID
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


@router.get("/invoices")
async def list_invoices(
    identity: TenantAdmin,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    confirmed_by: UUID | None = None,
    cif_status: str | None = None,
    company_id: UUID | None = None,
    cursor: str | None = None,
) -> PanelOut:
    """Facturas confirmadas de la asesoría, filtradas y paginadas (S3.1). Ver spec S3.1."""
    filters = service.PanelFilters(
        date_from=date_from,
        date_to=date_to,
        q=q,
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
