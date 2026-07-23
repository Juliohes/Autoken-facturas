"""Acceso a datos de la persistencia de facturas (S2.5): SQL de invoices/tax_lines/ocr_corrections.

La sesión llega ya abierta en el contexto de aislamiento del tenant (S1.1): la RLS de dos niveles
decide qué filas se ven y se escriben. El `tenant_id` de las escrituras NO viaja por parámetro: sale
de `app.tenant_id` (la misma fuente que la RLS), de modo que ninguna fila cruce el tenant de la
petición. Todas las escrituras participan en la transacción de la petición (atomicidad, spec §4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoicing.corrections import Correction
from shared.integrity import violates_unique_constraint

logger = structlog.get_logger("invoicing")

# `tenant_id` de las escrituras derivado del contexto de la sesión (coherente con la RLS).
_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# Nombre del UNIQUE `(uploaded_file_id)` (migración 0007): red última de "una factura por fichero",
# resistente a la carrera de dos confirmaciones concurrentes (C9). Traduce su violación a un 409.
_UPLOADED_FILE_UNIQUE = "invoices_uploaded_file_unique"

# Ventana móvil del historial (S2.6 spec §2/§4): facturas confirmadas en los últimos N días.
HISTORY_WINDOW_DAYS = 7

# Cota defensiva de resultados del historial (S2.6 spec §4): la ventana de 7 días ya acota el
# volumen; esta cota es la red última contra una lista sin fin.
HISTORY_LIMIT = 200


@dataclass(frozen=True)
class HistoryEntry:
    """Una entrada del historial de facturas confirmadas (S2.6, spec §2)."""

    id: UUID
    issue_date: date | None
    direction: str
    counterparty_tax_id: str | None
    counterparty_name: str | None
    counterparty_cif_status: str
    total_amount: Decimal | None
    confirmed_at: datetime


@dataclass(frozen=True)
class InvoiceRecord:
    """Estado actual de una factura confirmada, para calcular el diff de una edición (S3.3).

    `tax_lines` en bruto (tuplas `(iva_pct, base, cuota)`, como `insert_tax_lines`): el repositorio
    no conoce el tipo `ocr.verification.TaxLine` (es del contexto `ocr`); esa conversión es del
    servicio, igual que ya hace con los tramos de la extracción OCR (`_extraction_tax_lines`).
    """

    id: UUID
    company_id: UUID
    issue_date: date | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    counterparty_cif_status: str
    net_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    irpf_amount: Decimal | None
    tax_lines: list[tuple[Decimal | None, Decimal | None, Decimal | None]]


def is_duplicate_invoice(exc: IntegrityError) -> bool:
    """True si la `IntegrityError` viene del UNIQUE `(uploaded_file_id)` de `invoices`."""
    return violates_unique_constraint(exc, _UPLOADED_FILE_UNIQUE)


async def get_invoice(session: AsyncSession, invoice_id: UUID) -> InvoiceRecord | None:
    """Estado actual de una factura visible en el contexto (RLS), o `None` (S3.3).

    Usado para calcular el diff de una edición contra el valor anterior; sin filtro de
    `tenant_id`/`company_id` por parámetro (la RLS de dos niveles ya acota, igual que el resto del
    contexto).
    """
    row = (
        await session.execute(
            text(
                "SELECT id, company_id, issue_date, counterparty_tax_id, counterparty_name, "
                " counterparty_cif_status, net_amount, tax_amount, total_amount, irpf_amount "
                "FROM invoices WHERE id = :id"
            ),
            {"id": str(invoice_id)},
        )
    ).first()
    if row is None:
        return None
    lines = (
        await session.execute(
            text("SELECT iva_pct, base, cuota FROM invoice_tax_lines WHERE invoice_id = :id"),
            {"id": str(invoice_id)},
        )
    ).all()
    return InvoiceRecord(
        id=row.id,
        company_id=row.company_id,
        issue_date=row.issue_date,
        counterparty_tax_id=row.counterparty_tax_id,
        counterparty_name=row.counterparty_name,
        counterparty_cif_status=row.counterparty_cif_status,
        net_amount=row.net_amount,
        tax_amount=row.tax_amount,
        total_amount=row.total_amount,
        irpf_amount=row.irpf_amount,
        tax_lines=[(line.iva_pct, line.base, line.cuota) for line in lines],
    )


async def update_invoice(
    session: AsyncSession,
    invoice_id: UUID,
    *,
    issue_date: date | None,
    counterparty_tax_id: str | None,
    counterparty_name: str | None,
    counterparty_cif_status: str,
    net_amount: Decimal | None,
    tax_amount: Decimal | None,
    total_amount: Decimal | None,
    irpf_amount: Decimal | None,
    balance_ok: bool | None,
) -> None:
    """Actualiza los campos editables de una factura ya confirmada (S3.3). Siempre el conjunto
    completo (el servicio ya fusionó el `PATCH` parcial con el valor anterior): evita construir SQL
    con una lista de columnas dinámica."""
    await session.execute(
        text(
            "UPDATE invoices SET issue_date = :issue_date, "
            " counterparty_tax_id = :counterparty_tax_id, counterparty_name = :counterparty_name, "
            " counterparty_cif_status = :counterparty_cif_status, net_amount = :net_amount, "
            " tax_amount = :tax_amount, total_amount = :total_amount, "
            " irpf_amount = :irpf_amount, balance_ok = :balance_ok "
            "WHERE id = :id"
        ),
        {
            "id": str(invoice_id),
            "issue_date": issue_date,
            "counterparty_tax_id": counterparty_tax_id,
            "counterparty_name": counterparty_name,
            "counterparty_cif_status": counterparty_cif_status,
            "net_amount": net_amount,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "irpf_amount": irpf_amount,
            "balance_ok": balance_ok,
        },
    )


async def invoice_exists_for_file(session: AsyncSession, uploaded_file_id: UUID) -> bool:
    """True si ya hay una factura para ese fichero en el contexto (una factura por fichero, C9)."""
    row = (
        await session.execute(
            text("SELECT 1 FROM invoices WHERE uploaded_file_id = :fid LIMIT 1"),
            {"fid": str(uploaded_file_id)},
        )
    ).first()
    return row is not None


async def insert_invoice(
    session: AsyncSession,
    *,
    company_id: UUID,
    uploaded_file_id: UUID,
    direction: str,
    issue_date: date | None,
    counterparty_tax_id: str | None,
    counterparty_name: str | None,
    counterparty_cif_status: str,
    net_amount: Decimal | None,
    tax_amount: Decimal | None,
    total_amount: Decimal | None,
    irpf_amount: Decimal | None,
    is_test: bool,
    balance_ok: bool | None,
    snapshot: dict[str, Any],
    confirmed_by: UUID,
) -> UUID:
    """Inserta la factura confirmada en el tenant del contexto y devuelve su id.

    `status` es siempre `confirmed` (fuente única del estado de una factura confirmada, S2.5).
    Puede lanzar `IntegrityError` del UNIQUE `(uploaded_file_id)` si otra confirmación concurrente
    ganó la carrera; el llamante ya comprobó la existencia antes (C9); el UNIQUE es la red.
    """
    row = (
        await session.execute(
            text(
                f"INSERT INTO invoices "
                f"(tenant_id, company_id, uploaded_file_id, direction, issue_date, "
                f" counterparty_tax_id, counterparty_name, counterparty_cif_status, "
                f" net_amount, tax_amount, total_amount, irpf_amount, is_test, balance_ok, "
                f" snapshot, status, confirmed_by) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :uploaded_file_id, :direction, "
                f" :issue_date, :counterparty_tax_id, :counterparty_name, "
                f" :counterparty_cif_status, "
                f" :net_amount, :tax_amount, :total_amount, :irpf_amount, :is_test, :balance_ok, "
                f" CAST(:snapshot AS jsonb), 'confirmed', :confirmed_by) "
                f"RETURNING id"
            ),
            {
                "company_id": str(company_id),
                "uploaded_file_id": str(uploaded_file_id),
                "direction": direction,
                "issue_date": issue_date,
                "counterparty_tax_id": counterparty_tax_id,
                "counterparty_name": counterparty_name,
                "counterparty_cif_status": counterparty_cif_status,
                "net_amount": net_amount,
                "tax_amount": tax_amount,
                "total_amount": total_amount,
                "irpf_amount": irpf_amount,
                "is_test": is_test,
                "balance_ok": balance_ok,
                "snapshot": json.dumps(snapshot),
                "confirmed_by": str(confirmed_by),
            },
        )
    ).one()
    invoice_id: UUID = row.id
    return invoice_id


async def insert_tax_lines(
    session: AsyncSession,
    *,
    invoice_id: UUID,
    company_id: UUID,
    lines: list[tuple[Decimal | None, Decimal | None, Decimal | None]],
) -> None:
    """Inserta los tramos de IVA confirmados (`(iva_pct, base, cuota)`) de la factura."""
    for iva_pct, base, cuota in lines:
        await session.execute(
            text(
                f"INSERT INTO invoice_tax_lines "
                f"(tenant_id, company_id, invoice_id, iva_pct, base, cuota) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :invoice_id, :iva_pct, :base, "
                f":cuota)"
            ),
            {
                "company_id": str(company_id),
                "invoice_id": str(invoice_id),
                "iva_pct": iva_pct,
                "base": base,
                "cuota": cuota,
            },
        )


async def delete_tax_lines(session: AsyncSession, invoice_id: UUID) -> None:
    """Borra todos los tramos de IVA de una factura (S3.3): el reemplazo completo de `tax_lines` en
    una edición es un borra-e-inserta, no un `UPDATE` fila a fila (spec §2 C6)."""
    await session.execute(
        text("DELETE FROM invoice_tax_lines WHERE invoice_id = :invoice_id"),
        {"invoice_id": str(invoice_id)},
    )


@dataclass(frozen=True)
class PurgedInvoice:
    """Una factura de prueba borrada por la purga (S3.5): su id y el fichero subido asociado."""

    id: UUID
    uploaded_file_id: UUID


async def purge_test_invoices(session: AsyncSession) -> list[PurgedInvoice]:
    """Borra TODAS las facturas `is_test = true` visibles en el contexto y las devuelve (S3.5).

    La condición `is_test = true` es fija en esta sentencia, nunca un parámetro (spec S3.5 regla de
    dominio 2): estructuralmente no puede alcanzar una factura real. El borrado arrastra en cascada
    `invoice_tax_lines`/`ocr_corrections`/`invoice_edits` (ya declarado en el esquema, 0007/0008);
    `uploaded_files` se borra aparte (la cascada solo va de `uploaded_files` hacia `invoices`, no al
    revés), de ahí que se devuelva también `uploaded_file_id` de cada fila borrada.
    """
    rows = (
        await session.execute(
            text("DELETE FROM invoices WHERE is_test = true RETURNING id, uploaded_file_id")
        )
    ).all()
    return [PurgedInvoice(id=row.id, uploaded_file_id=row.uploaded_file_id) for row in rows]


async def insert_corrections(
    session: AsyncSession,
    *,
    invoice_id: UUID,
    uploaded_file_id: UUID,
    company_id: UUID,
    corrected_by: UUID,
    corrections: list[Correction],
) -> None:
    """Inserta una fila por corrección (campo que el humano cambió respecto al OCR, C2)."""
    for correction in corrections:
        await session.execute(
            text(
                f"INSERT INTO ocr_corrections "
                f"(tenant_id, company_id, invoice_id, uploaded_file_id, field, ai_value, "
                f" human_value, corrected_by) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :invoice_id, :uploaded_file_id, "
                f" :field, :ai_value, :human_value, :corrected_by)"
            ),
            {
                "company_id": str(company_id),
                "invoice_id": str(invoice_id),
                "uploaded_file_id": str(uploaded_file_id),
                "field": correction.field,
                "ai_value": correction.ai_value,
                "human_value": correction.human_value,
                "corrected_by": str(corrected_by),
            },
        )


async def insert_edits(
    session: AsyncSession,
    *,
    invoice_id: UUID,
    company_id: UUID,
    edited_by: UUID,
    edits: list[Correction],
) -> None:
    """Inserta una fila por campo que cambió en una edición post-confirmación (S3.3, spec §2).

    Reutiliza `Correction` (mismo diff que `ocr_corrections`, `invoicing.corrections`): `ai_value`
    es aquí el valor ANTERIOR de la factura, `human_value` el editado (nombres del dataclass
    genéricos; las columnas de `invoice_edits` sí se llaman `old_value`/`new_value`, más precisas
    para este caso de uso humano-vs-humano).
    """
    for edit in edits:
        await session.execute(
            text(
                f"INSERT INTO invoice_edits "
                f"(tenant_id, company_id, invoice_id, field, old_value, new_value, edited_by) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :invoice_id, :field, :old_value, "
                f" :new_value, :edited_by)"
            ),
            {
                "company_id": str(company_id),
                "invoice_id": str(invoice_id),
                "field": edit.field,
                "old_value": edit.ai_value,
                "new_value": edit.human_value,
                "edited_by": str(edited_by),
            },
        )


async def list_history(session: AsyncSession) -> list[HistoryEntry]:
    """Facturas confirmadas de los últimos 7 días del contexto (S2.6), la más reciente primero.

    Sin filtro de `tenant_id`/`company_id` por parámetro: la RLS de dos niveles de `invoices`
    (migración 0007) ya acota el resultado al contexto de la sesión (spec §4, anti-cruce de
    tenants). Excluye `is_test` (regla 3) y aplica la cota defensiva `HISTORY_LIMIT`; si se alcanza,
    se registra (spec §5: nunca se trunca en silencio como si fuera todo).
    """
    rows = (
        await session.execute(
            text(
                "SELECT id, issue_date, direction, counterparty_tax_id, counterparty_name, "
                " counterparty_cif_status, total_amount, confirmed_at "
                "FROM invoices "
                "WHERE is_test = false AND confirmed_at >= "
                f"now() - interval '{HISTORY_WINDOW_DAYS} days' "
                "ORDER BY confirmed_at DESC "
                "LIMIT :limit"
            ),
            {"limit": HISTORY_LIMIT},
        )
    ).all()
    if len(rows) == HISTORY_LIMIT:
        logger.warning("invoice_history.limit_reached", limit=HISTORY_LIMIT)
    return [
        HistoryEntry(
            id=row.id,
            issue_date=row.issue_date,
            direction=row.direction,
            counterparty_tax_id=row.counterparty_tax_id,
            counterparty_name=row.counterparty_name,
            counterparty_cif_status=row.counterparty_cif_status,
            total_amount=row.total_amount,
            confirmed_at=row.confirmed_at,
        )
        for row in rows
    ]
