"""Lógica de dominio del panel de facturas (S3.1), su export a Excel (S3.2) y la ficha agregada de
empresas (S3.4).

El router HTTP es fino: traduce la petición a `list_invoices`/`export_invoices`/`list_companies` y
sus excepciones de dominio a códigos HTTP. Aquí vive la validación del rango de fechas (compartida
por panel y export) y la codificación/decodificación del cursor de paginación (opaco para el
cliente, spec S3.1 §2); `list_companies` (S3.4) no pagina, así que no la necesita.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from identity.dependencies import AuthContext
from reporting import repository
from shared.config import get_settings
from shared.encryption import tenant_encryption_key, tenant_tax_id_blind_index


class ReportingError(Exception):
    """Raíz de los errores de dominio del panel de facturas."""


class InvalidDateRange(ReportingError):
    """`date_from` posterior a `date_to` (-> 422, spec §5)."""


class InvalidCursor(ReportingError):
    """El cursor no se puede decodificar (-> 422, spec §5)."""


@dataclass(frozen=True)
class PanelFilters:
    """Filtros del panel tal como los recibe el router, ya tipados (spec §2, S5.2 C5).

    `counterparty_tax_id`: filtro EXACTO por CIF de contraparte (vía índice ciego, spec S5.2 C5).
    Sustituye al antiguo `q` de texto libre (`ILIKE` sobre nombre/CIF), retirado porque el nombre
    de contraparte vive cifrado sin índice ciego desde S5.2 (decisión de Julio).
    """

    date_from: date | None = None
    date_to: date | None = None
    counterparty_tax_id: str | None = None
    confirmed_by: UUID | None = None
    cif_status: str | None = None
    company_id: UUID | None = None


@dataclass(frozen=True)
class TaxLineItem:
    """Un tramo de IVA de una fila del panel, contrato propio del servicio."""

    iva_pct: Decimal | None
    base: Decimal | None
    cuota: Decimal | None


@dataclass(frozen=True)
class InvoiceItem:
    """Una fila del panel de facturas (S3.1), contrato propio del servicio.

    No reexporta `repository.InvoiceRow` tal cual: el router no debe depender de la forma interna
    de la capa de persistencia (mismo criterio que `invoicing.service.HistoryItem`, S2.6).
    """

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
    tax_lines: list[TaxLineItem]
    confirmed_at: datetime
    confirmed_by: UUID
    uploaded_file_id: UUID
    uploaded_at: datetime


@dataclass(frozen=True)
class PanelPage:
    """Una página del panel: sus filas y el cursor de la siguiente (o `None` si es la última)."""

    items: list[InvoiceItem]
    next_cursor: str | None


@dataclass(frozen=True)
class ExportItem:
    """Una fila del export a Excel (S3.2), contrato propio del servicio.

    No reexporta `repository.ExportRow` tal cual, mismo criterio que `InvoiceItem` (S3.1).
    """

    company_name: str
    issue_date: date | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    counterparty_cif_status: str
    net_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    irpf_amount: Decimal | None
    tax_lines: list[TaxLineItem]
    uploaded_at: datetime
    confirmed_by_email: str


@dataclass(frozen=True)
class CompanySummary:
    """Una fila de la ficha agregada de empresas (S3.4), contrato propio del servicio.

    No reexporta `repository.CompanyRow` tal cual, mismo criterio que `InvoiceItem` (S3.1).
    """

    id: UUID
    name: str
    cif: str
    status: str
    notes: str | None
    created_at: datetime
    user_count: int
    invoice_count: int
    last_invoice_at: datetime | None


def _to_company_summary(row: repository.CompanyRow) -> CompanySummary:
    return CompanySummary(
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


async def list_companies(identity: AuthContext) -> list[CompanySummary]:
    """Ficha agregada de las empresas de la asesoría del `tenant_admin` (S3.4). Solo lectura."""
    rows = await repository.list_companies(
        identity.session,
        encryption_key=tenant_encryption_key(get_settings(), identity.tenant_id),
    )
    return [_to_company_summary(row) for row in rows]


def _validate_date_range(filters: PanelFilters) -> None:
    """`date_from` posterior a `date_to` -> `InvalidDateRange` (compartido por panel y export)."""
    if (
        filters.date_from is not None
        and filters.date_to is not None
        and filters.date_from > filters.date_to
    ):
        raise InvalidDateRange


def _repo_filters(tenant_id: UUID, filters: PanelFilters) -> repository.Filters:
    """Traduce los filtros del servicio a los del repositorio (compartido por panel y export)."""
    return repository.Filters(
        date_from=filters.date_from,
        date_to=filters.date_to,
        counterparty_tax_id_blind_index=tenant_tax_id_blind_index(
            get_settings(), tenant_id, filters.counterparty_tax_id
        ),
        confirmed_by=filters.confirmed_by,
        cif_status=filters.cif_status,
        company_id=filters.company_id,
    )


def _to_item(row: repository.InvoiceRow) -> InvoiceItem:
    return InvoiceItem(
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
            TaxLineItem(iva_pct=t.iva_pct, base=t.base, cuota=t.cuota) for t in row.tax_lines
        ],
        confirmed_at=row.confirmed_at,
        confirmed_by=row.confirmed_by,
        uploaded_file_id=row.uploaded_file_id,
        uploaded_at=row.uploaded_at,
    )


def _to_export_item(row: repository.ExportRow) -> ExportItem:
    return ExportItem(
        company_name=row.company_name,
        issue_date=row.issue_date,
        counterparty_tax_id=row.counterparty_tax_id,
        counterparty_name=row.counterparty_name,
        counterparty_cif_status=row.counterparty_cif_status,
        net_amount=row.net_amount,
        tax_amount=row.tax_amount,
        total_amount=row.total_amount,
        irpf_amount=row.irpf_amount,
        tax_lines=[
            TaxLineItem(iva_pct=t.iva_pct, base=t.base, cuota=t.cuota) for t in row.tax_lines
        ],
        uploaded_at=row.uploaded_at,
        confirmed_by_email=row.confirmed_by_email,
    )


def _encode_cursor(confirmed_at: datetime, invoice_id: UUID) -> str:
    """Codifica el cursor como opaco (base64) para que el cliente no lo interprete ni lo module."""
    raw = f"{confirmed_at.isoformat()}|{invoice_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> repository.Cursor:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        iso, id_str = raw.split("|", 1)
        return repository.Cursor(confirmed_at=datetime.fromisoformat(iso), id=UUID(id_str))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursor from exc


async def list_invoices(
    identity: AuthContext, filters: PanelFilters, cursor: str | None
) -> PanelPage:
    """Página de facturas confirmadas de la asesoría del `tenant_admin` (S3.1). Solo lectura."""
    _validate_date_range(filters)
    decoded_cursor = _decode_cursor(cursor) if cursor is not None else None

    rows = await repository.list_invoices(
        identity.session,
        filters=_repo_filters(identity.tenant_id, filters),
        cursor=decoded_cursor,
        encryption_key=tenant_encryption_key(get_settings(), identity.tenant_id),
    )

    has_more = len(rows) > repository.PAGE_SIZE
    page = rows[: repository.PAGE_SIZE]
    next_cursor = _encode_cursor(page[-1].confirmed_at, page[-1].id) if has_more and page else None
    return PanelPage(items=[_to_item(row) for row in page], next_cursor=next_cursor)


async def export_invoices(identity: AuthContext, filters: PanelFilters) -> list[ExportItem]:
    """Todas las facturas que casan los filtros, sin paginar, para el export a Excel (S3.2)."""
    _validate_date_range(filters)
    rows = await repository.list_for_export(
        identity.session,
        filters=_repo_filters(identity.tenant_id, filters),
        encryption_key=tenant_encryption_key(get_settings(), identity.tenant_id),
    )
    return [_to_export_item(row) for row in rows]
