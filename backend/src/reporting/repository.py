"""Acceso a datos del panel de facturas (S3.1): lectura filtrada/paginada de `invoices`.

`reporting` es un contexto de **solo lectura** (estilo CQRS): no posee `invoices`/
`invoice_tax_lines` (los posee `invoicing`) ni `uploaded_files` (los posee `invoice_intake`), pero
necesita consultarlos juntos, filtrados y paginados, para el panel de la asesoría. Igual que el
resto de repositorios del proyecto, la sesión llega ya abierta en el contexto de aislamiento del
tenant (RLS de dos niveles, migraciones 0001/0004/0007); `reporting` nunca escribe, solo lee.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# Tamaño de página fijo (spec S3.1 §4): no configurable por el cliente.
PAGE_SIZE = 50


@dataclass(frozen=True)
class TaxLineRow:
    """Un tramo de IVA de una factura, tal cual se guardó al confirmar (S2.5)."""

    iva_pct: Decimal | None
    base: Decimal | None
    cuota: Decimal | None


@dataclass(frozen=True)
class InvoiceRow:
    """Una fila del panel de facturas (S3.1, spec §2/§3 C8)."""

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
    confirmed_at: datetime
    confirmed_by: UUID
    uploaded_file_id: UUID
    uploaded_at: datetime
    tax_lines: list[TaxLineRow]


@dataclass(frozen=True)
class Filters:
    """Filtros del panel, todos opcionales y combinables por AND (spec §2)."""

    date_from: date | None = None
    date_to: date | None = None
    q: str | None = None
    confirmed_by: UUID | None = None
    cif_status: str | None = None
    company_id: UUID | None = None


@dataclass(frozen=True)
class Cursor:
    """Posición de continuación de la paginación: última fila vista (`confirmed_at`, `id`)."""

    confirmed_at: datetime
    id: UUID


def _escape_ilike(value: str) -> str:
    """Escapa `\\`, `%` y `_` de un texto libre antes de envolverlo en un `ILIKE` (spec C3).

    Sin esto, un usuario que buscara literalmente "50%" (p. ej. un descuento en el nombre del
    proveedor) casaría de más: `%` e `_` son comodines de `LIKE`/`ILIKE`, no texto literal.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_where(filters: Filters, cursor: Cursor | None) -> tuple[str, dict[str, object]]:
    """Construye la cláusula `WHERE` y sus parámetros a partir de los filtros y el cursor.

    `is_test = false` es incondicional (regla 3, spec §2): las facturas de prueba nunca aparecen en
    el panel. Ningún valor de usuario se interpola en el SQL: todo va por parámetro ligado.
    """
    conditions = ["i.is_test = false"]
    params: dict[str, object] = {}
    if filters.date_from is not None:
        conditions.append("i.issue_date >= :date_from")
        params["date_from"] = filters.date_from
    if filters.date_to is not None:
        conditions.append("i.issue_date <= :date_to")
        params["date_to"] = filters.date_to
    if filters.q:
        conditions.append(
            "(i.counterparty_name ILIKE :q ESCAPE '\\' "
            "OR i.counterparty_tax_id ILIKE :q ESCAPE '\\')"
        )
        params["q"] = f"%{_escape_ilike(filters.q)}%"
    if filters.confirmed_by is not None:
        conditions.append("i.confirmed_by = :confirmed_by")
        params["confirmed_by"] = str(filters.confirmed_by)
    if filters.cif_status is not None:
        conditions.append("i.counterparty_cif_status = :cif_status")
        params["cif_status"] = filters.cif_status
    if filters.company_id is not None:
        conditions.append("i.company_id = :company_id")
        params["company_id"] = str(filters.company_id)
    if cursor is not None:
        conditions.append("(i.confirmed_at, i.id) < (:cursor_confirmed_at, :cursor_id)")
        params["cursor_confirmed_at"] = cursor.confirmed_at
        params["cursor_id"] = str(cursor.id)
    return " AND ".join(conditions), params


async def list_invoices(
    session: AsyncSession, *, filters: Filters, cursor: Cursor | None
) -> list[InvoiceRow]:
    """Página de facturas confirmadas del contexto (S3.1), filtradas y ordenadas.

    Sin filtro de `tenant_id`/`company_id` de sesión por parámetro: la RLS de dos niveles de
    `invoices` (migración 0007) ya acota el resultado al tenant del `tenant_admin`; como su
    `app.company_id` no está fijado (asesoría completa, no una empresa), ve todas las suyas. Pide
    `PAGE_SIZE + 1` filas para que el servicio sepa si hay página siguiente sin una consulta aparte.
    """
    where, params = _build_where(filters, cursor)
    params["limit"] = PAGE_SIZE + 1
    rows = (
        await session.execute(
            text(
                "SELECT i.id, i.issue_date, i.direction, i.counterparty_tax_id, "
                " i.counterparty_name, i.counterparty_cif_status, i.net_amount, i.tax_amount, "
                " i.total_amount, i.irpf_amount, i.confirmed_at, i.confirmed_by, "
                " i.uploaded_file_id, uf.created_at AS uploaded_at "
                "FROM invoices i "
                "JOIN uploaded_files uf ON uf.id = i.uploaded_file_id "
                f"WHERE {where} "
                "ORDER BY i.confirmed_at DESC, i.id DESC "
                "LIMIT :limit"
            ),
            params,
        )
    ).all()

    tax_lines_by_invoice = await _tax_lines_for(session, [row.id for row in rows])
    return [
        InvoiceRow(
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
            confirmed_at=row.confirmed_at,
            confirmed_by=row.confirmed_by,
            uploaded_file_id=row.uploaded_file_id,
            uploaded_at=row.uploaded_at,
            tax_lines=tax_lines_by_invoice.get(row.id, []),
        )
        for row in rows
    ]


async def _tax_lines_for(
    session: AsyncSession, invoice_ids: list[UUID]
) -> dict[UUID, list[TaxLineRow]]:
    """Tramos de IVA de un lote de facturas, agrupados por `invoice_id` (evita N+1 por fila)."""
    if not invoice_ids:
        return {}
    stmt = text(
        "SELECT invoice_id, iva_pct, base, cuota FROM invoice_tax_lines WHERE invoice_id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    rows = (await session.execute(stmt, {"ids": [str(i) for i in invoice_ids]})).all()
    result: dict[UUID, list[TaxLineRow]] = {}
    for row in rows:
        result.setdefault(row.invoice_id, []).append(
            TaxLineRow(iva_pct=row.iva_pct, base=row.base, cuota=row.cuota)
        )
    return result
