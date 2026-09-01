"""Acceso a datos de la persistencia de facturas (S2.5): SQL de invoices/tax_lines/ocr_corrections.

La sesión llega ya abierta en el contexto de aislamiento del tenant (S1.1): la RLS de dos niveles
decide qué filas se ven y se escriben. El `tenant_id` de las escrituras NO viaja por parámetro: sale
de `app.tenant_id` (la misma fuente que la RLS), de modo que ninguna fila cruce el tenant de la
petición. Todas las escrituras participan en la transacción de la petición (atomicidad, spec §4).

`invoices.counterparty_tax_id`/`counterparty_name` viven cifrados desde S5.2 (`pgp_sym_encrypt`/
`pgp_sym_decrypt`, clave por tenant), con un índice ciego del CIF
(`counterparty_tax_id_blind_index`) que sustituye al filtro `ILIKE` retirado del panel (spec C5). El
repositorio recibe la clave y el índice ya calculados por `invoicing.service`; nunca deriva claves.
Nulos se conservan tal cual (anti-alucinación: contraparte no legible = NULL, spec §5) porque
`pgp_sym_encrypt`/`pgp_sym_decrypt` son funciones STRICT (NULL entra, NULL sale).
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

# El historial privado es una vista operativa de los últimos documentos aceptados, no un listado
# contable de facturas confirmadas. La cota es parte del contrato S6.12.
HISTORY_LIMIT = 20
INBOX_LIMIT = 20


@dataclass(frozen=True)
class HistoryEntry:
    """Una entrada sin PII del historial de documentos aceptados (S6.12).

    ``invoice_number`` es el número del documento propio (no dato de contraparte): mismo
    criterio que importes/fecha, exponerlo es aceptable (paso 8, ajustes UI). Solo llega
    cuando `list_history` encuentra una factura `confirmed`; nunca se inventa un valor.
    """

    id: UUID
    status: str
    created_at: datetime
    direction: str | None
    invoice_number: str | None


@dataclass(frozen=True)
class HistoryPage:
    entries: list[HistoryEntry]
    has_more: bool


@dataclass(frozen=True)
class InboxEntry:
    """Documento operativo de la bandeja personal, sin campos fiscales ni OCR (R-020)."""

    id: UUID
    status: str
    processing_stage: str | None
    created_at: datetime
    direction: str | None
    page_count: int
    capture_session_id: UUID | None
    capture_sequence: int | None


@dataclass(frozen=True)
class InboxSummary:
    processing: int
    ready: int
    attention: int


@dataclass(frozen=True)
class InboxPage:
    items: list[InboxEntry]
    summary: InboxSummary
    has_more: bool


@dataclass(frozen=True)
class SupervisionEntry:
    id: UUID
    user_email: str
    company_name: str
    status: str
    created_at: datetime
    direction: str | None
    page_count: int


@dataclass(frozen=True)
class SupervisionPage:
    items: list[SupervisionEntry]
    has_more: bool


@dataclass(frozen=True)
class InvoiceRecord:
    """Estado actual de una factura confirmada, para calcular el diff de una edición (S3.3) o para
    la Lectura 3 (guardado final) del laboratorio OCR (S6.2).

    `tax_lines` en bruto (tuplas `(iva_pct, base, cuota)`, como `insert_tax_lines`): el repositorio
    no conoce el tipo `ocr.verification.TaxLine` (es del contexto `ocr`); esa conversión es del
    servicio, igual que ya hace con los tramos de la extracción OCR (`extraction_tax_lines`).

    `uploaded_file_id`/`direction`/`invoice_number`/`is_test`/`balance_ok`/`status`/`confirmed_by`/
    `confirmed_at` (S6.2): `edit_invoice`/`get_invoice` no los necesitaban hasta ahora, pero
    `get_invoice_by_uploaded_file_id` sí (el laboratorio muestra la factura confirmada completa,
    spec C10) — se añaden aquí, no en un dataclass paralelo, para no duplicar la lectura de
    `invoices` en dos sitios (única fuente de verdad de "cómo se lee una factura").
    """

    id: UUID
    company_id: UUID
    uploaded_file_id: UUID
    direction: str
    issue_date: date | None
    invoice_number: str | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    counterparty_cif_status: str
    net_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    irpf_amount: Decimal | None
    is_test: bool
    balance_ok: bool | None
    own_tax_id_missing: bool
    own_tax_id_exception_confirmed: bool
    status: str
    confirmed_by: UUID
    confirmed_at: datetime
    tax_lines: list[tuple[Decimal | None, Decimal | None, Decimal | None]]


@dataclass(frozen=True)
class DuplicateCandidate:
    uploaded_file_id: UUID
    invoice_id: UUID | None
    invoice_number: str | None
    own_tax_id: str | None
    counterparty_tax_id: str | None
    total_amount: Decimal | None


def is_duplicate_invoice(exc: IntegrityError) -> bool:
    """True si la `IntegrityError` viene del UNIQUE `(uploaded_file_id)` de `invoices`."""
    return violates_unique_constraint(exc, _UPLOADED_FILE_UNIQUE)


# Columnas comunes a `get_invoice`/`get_invoice_by_uploaded_file_id` (S6.2): única fuente de
# verdad de "cómo se lee una factura confirmada", solo cambia el `WHERE`.
_INVOICE_COLUMNS = (
    "id, company_id, uploaded_file_id, direction, issue_date, invoice_number, "
    "pgp_sym_decrypt(counterparty_tax_id, :key)::text AS counterparty_tax_id, "
    "pgp_sym_decrypt(counterparty_name, :key)::text AS counterparty_name, "
    "counterparty_cif_status, net_amount, tax_amount, total_amount, irpf_amount, "
    "is_test, balance_ok, own_tax_id_missing, own_tax_id_exception_confirmed, "
    "status, confirmed_by, confirmed_at"
)


async def _tax_lines_for_invoice(
    session: AsyncSession, invoice_id: UUID
) -> list[tuple[Decimal | None, Decimal | None, Decimal | None]]:
    lines = (
        await session.execute(
            text("SELECT iva_pct, base, cuota FROM invoice_tax_lines WHERE invoice_id = :id"),
            {"id": str(invoice_id)},
        )
    ).all()
    return [(line.iva_pct, line.base, line.cuota) for line in lines]


def _to_invoice_record(
    row: Any, tax_lines: list[tuple[Decimal | None, Decimal | None, Decimal | None]]
) -> InvoiceRecord:
    return InvoiceRecord(
        id=row.id,
        company_id=row.company_id,
        uploaded_file_id=row.uploaded_file_id,
        direction=row.direction,
        issue_date=row.issue_date,
        invoice_number=row.invoice_number,
        counterparty_tax_id=row.counterparty_tax_id,
        counterparty_name=row.counterparty_name,
        counterparty_cif_status=row.counterparty_cif_status,
        net_amount=row.net_amount,
        tax_amount=row.tax_amount,
        total_amount=row.total_amount,
        irpf_amount=row.irpf_amount,
        is_test=row.is_test,
        balance_ok=row.balance_ok,
        own_tax_id_missing=row.own_tax_id_missing,
        own_tax_id_exception_confirmed=row.own_tax_id_exception_confirmed,
        status=row.status,
        confirmed_by=row.confirmed_by,
        confirmed_at=row.confirmed_at,
        tax_lines=tax_lines,
    )


async def get_invoice(
    session: AsyncSession, invoice_id: UUID, *, encryption_key: str
) -> InvoiceRecord | None:
    """Estado actual de una factura visible en el contexto (RLS), o `None` (S3.3).

    Usado para calcular el diff de una edición contra el valor anterior; sin filtro de
    `tenant_id`/`company_id` por parámetro (la RLS de dos niveles ya acota, igual que el resto del
    contexto).
    """
    row = (
        await session.execute(
            text(f"SELECT {_INVOICE_COLUMNS} FROM invoices WHERE id = :id"),  # noqa: S608
            {"id": str(invoice_id), "key": encryption_key},
        )
    ).first()
    if row is None:
        return None
    return _to_invoice_record(row, await _tax_lines_for_invoice(session, invoice_id))


async def get_invoice_by_uploaded_file_id(
    session: AsyncSession, uploaded_file_id: UUID, *, encryption_key: str
) -> InvoiceRecord | None:
    """Estado actual de la factura confirmada de un fichero visible en el contexto (RLS), o `None`.

    Usado por el laboratorio OCR (S6.2, Lectura 3): a diferencia de `get_invoice` (por `invoice_id`,
    S3.3), el laboratorio arranca de un `uploaded_file_id` (spec C10). `None` cubre tanto "no existe
    ninguna factura para ese fichero" como "el fichero pertenece a otro tenant" (la RLS de dos
    niveles lo hace invisible sin ninguna comprobación manual adicional, spec C5).
    """
    row = (
        await session.execute(
            text(  # noqa: S608
                f"SELECT {_INVOICE_COLUMNS} FROM invoices WHERE uploaded_file_id = :fid"
            ),
            {"fid": str(uploaded_file_id), "key": encryption_key},
        )
    ).first()
    if row is None:
        return None
    return _to_invoice_record(row, await _tax_lines_for_invoice(session, row.id))


async def update_invoice(
    session: AsyncSession,
    invoice_id: UUID,
    *,
    issue_date: date | None,
    counterparty_tax_id: str | None,
    counterparty_tax_id_blind_index: str | None,
    counterparty_name: str | None,
    counterparty_cif_status: str,
    net_amount: Decimal | None,
    tax_amount: Decimal | None,
    total_amount: Decimal | None,
    irpf_amount: Decimal | None,
    balance_ok: bool | None,
    encryption_key: str,
) -> None:
    """Actualiza los campos editables de una factura ya confirmada (S3.3). Siempre el conjunto
    completo (el servicio ya fusionó el `PATCH` parcial con el valor anterior): evita construir SQL
    con una lista de columnas dinámica."""
    await session.execute(
        text(
            "UPDATE invoices SET issue_date = :issue_date, "
            " counterparty_tax_id = pgp_sym_encrypt(:counterparty_tax_id, :key), "
            " counterparty_tax_id_blind_index = :counterparty_tax_id_blind_index, "
            " counterparty_name = pgp_sym_encrypt(:counterparty_name, :key), "
            " counterparty_cif_status = :counterparty_cif_status, net_amount = :net_amount, "
            " tax_amount = :tax_amount, total_amount = :total_amount, "
            " irpf_amount = :irpf_amount, balance_ok = :balance_ok "
            "WHERE id = :id"
        ),
        {
            "id": str(invoice_id),
            "issue_date": issue_date,
            "counterparty_tax_id": counterparty_tax_id,
            "counterparty_tax_id_blind_index": counterparty_tax_id_blind_index,
            "counterparty_name": counterparty_name,
            "counterparty_cif_status": counterparty_cif_status,
            "net_amount": net_amount,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "irpf_amount": irpf_amount,
            "balance_ok": balance_ok,
            "key": encryption_key,
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


async def list_duplicate_candidates(
    session: AsyncSession,
    *,
    company_id: UUID,
    uploaded_file_id: UUID,
    encryption_key: str,
) -> list[DuplicateCandidate]:
    """Lee candidatos confirmados y OCR visibles de la misma empresa, sin cruzar RLS."""
    rows = (
        await session.execute(
            text(
                "SELECT i.uploaded_file_id, i.id AS invoice_id, i.invoice_number, "
                "pgp_sym_decrypt(c.cif, :key)::text AS own_tax_id, "
                "pgp_sym_decrypt(i.counterparty_tax_id, :key)::text "
                "AS counterparty_tax_id, i.total_amount "
                "FROM invoices i JOIN companies c ON c.id = i.company_id "
                "WHERE i.company_id = :company_id AND i.uploaded_file_id <> :file_id "
                "UNION ALL "
                "SELECT e.uploaded_file_id, NULL AS invoice_id, e.invoice_number, "
                "pgp_sym_decrypt(c.cif, :key)::text AS own_tax_id, "
                "pgp_sym_decrypt(e.counterparty_tax_id, :key)::text "
                "AS counterparty_tax_id, e.total_amount "
                "FROM ocr_extractions e "
                "JOIN uploaded_files f ON f.id = e.uploaded_file_id "
                "JOIN companies c ON c.id = f.company_id "
                "WHERE f.company_id = :company_id AND e.uploaded_file_id <> :file_id "
                "UNION ALL "
                "SELECT d.uploaded_file_id, NULL AS invoice_id, d.invoice_number, "
                "pgp_sym_decrypt(c.cif, :key)::text AS own_tax_id, "
                "pgp_sym_decrypt(d.counterparty_tax_id, :key)::text AS counterparty_tax_id, "
                "d.total_amount "
                "FROM review_drafts d "
                "JOIN uploaded_files f ON f.id = d.uploaded_file_id "
                "JOIN companies c ON c.id = f.company_id "
                "WHERE f.company_id = :company_id AND d.uploaded_file_id <> :file_id"
            ),
            {
                "company_id": str(company_id),
                "file_id": str(uploaded_file_id),
                "key": encryption_key,
            },
        )
    ).all()
    return [
        DuplicateCandidate(
            uploaded_file_id=row.uploaded_file_id,
            invoice_id=row.invoice_id,
            invoice_number=row.invoice_number,
            own_tax_id=row.own_tax_id,
            counterparty_tax_id=row.counterparty_tax_id,
            total_amount=row.total_amount,
        )
        for row in rows
    ]


async def insert_invoice(
    session: AsyncSession,
    *,
    company_id: UUID,
    uploaded_file_id: UUID,
    direction: str,
    issue_date: date | None,
    counterparty_tax_id: str | None,
    counterparty_tax_id_blind_index: str | None,
    counterparty_name: str | None,
    counterparty_cif_status: str,
    invoice_number: str | None,
    net_amount: Decimal | None,
    tax_amount: Decimal | None,
    total_amount: Decimal | None,
    irpf_amount: Decimal | None,
    is_test: bool,
    balance_ok: bool | None,
    own_tax_id_missing: bool,
    own_tax_id_exception_confirmed: bool,
    snapshot: dict[str, Any],
    confirmed_by: UUID,
    encryption_key: str,
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
                f" counterparty_tax_id, counterparty_tax_id_blind_index, counterparty_name, "
                f" counterparty_cif_status, invoice_number, "
                f" net_amount, tax_amount, total_amount, irpf_amount, is_test, balance_ok, "
                f" own_tax_id_missing, own_tax_id_exception_confirmed, "
                f" snapshot, status, confirmed_by) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :uploaded_file_id, :direction, "
                f" :issue_date, pgp_sym_encrypt(:counterparty_tax_id, :key), "
                f" :counterparty_tax_id_blind_index, pgp_sym_encrypt(:counterparty_name, :key), "
                f" :counterparty_cif_status, :invoice_number, "
                f" :net_amount, :tax_amount, :total_amount, :irpf_amount, :is_test, :balance_ok, "
                f" :own_tax_id_missing, :own_tax_id_exception_confirmed, "
                f" CAST(:snapshot AS jsonb), 'confirmed', :confirmed_by) "
                f"RETURNING id"
            ),
            {
                "company_id": str(company_id),
                "uploaded_file_id": str(uploaded_file_id),
                "direction": direction,
                "issue_date": issue_date,
                "counterparty_tax_id": counterparty_tax_id,
                "counterparty_tax_id_blind_index": counterparty_tax_id_blind_index,
                "counterparty_name": counterparty_name,
                "counterparty_cif_status": counterparty_cif_status,
                "invoice_number": invoice_number,
                "net_amount": net_amount,
                "tax_amount": tax_amount,
                "total_amount": total_amount,
                "irpf_amount": irpf_amount,
                "is_test": is_test,
                "balance_ok": balance_ok,
                "own_tax_id_missing": own_tax_id_missing,
                "own_tax_id_exception_confirmed": own_tax_id_exception_confirmed,
                "snapshot": json.dumps(snapshot),
                "confirmed_by": str(confirmed_by),
                "key": encryption_key,
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


@dataclass(frozen=True)
class CorrectionEntry:
    """Una fila de `ocr_corrections`: un campo que el humano cambió respecto al OCR al confirmar
    (S2.5), tal como la muestra la Lectura 3 del laboratorio OCR (S6.2, spec C10)."""

    field: str
    ai_value: str | None
    human_value: str | None
    corrected_by: UUID
    created_at: datetime


async def list_corrections(session: AsyncSession, uploaded_file_id: UUID) -> list[CorrectionEntry]:
    """Correcciones de un fichero visibles en el contexto (RLS), más antigua primero (S6.2).

    `ocr_corrections` es append-only y hoy solo se escribe una vez, al confirmar (S2.5): no hay
    ambigüedad de orden real, pero se ordena igualmente por claridad (spec C10, "las 2
    correcciones").
    """
    rows = (
        await session.execute(
            text(
                "SELECT field, ai_value, human_value, corrected_by, created_at "
                "FROM ocr_corrections WHERE uploaded_file_id = :fid ORDER BY created_at"
            ),
            {"fid": str(uploaded_file_id)},
        )
    ).all()
    return [
        CorrectionEntry(
            field=row.field,
            ai_value=row.ai_value,
            human_value=row.human_value,
            corrected_by=row.corrected_by,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def count_corrections(session: AsyncSession, uploaded_file_id: UUID) -> int:
    """Cuenta las correcciones humanas registradas para una factura confirmada."""
    count = await session.scalar(
        text("SELECT count(*) FROM ocr_corrections WHERE uploaded_file_id = :fid"),
        {"fid": str(uploaded_file_id)},
    )
    return int(count or 0)


# Campos sensibles cuyo old_value/new_value en `invoice_edits` se cifran (spec S5.2 C7): el resto
# (importe, fecha, líneas de IVA...) sigue en claro, como antes de S5.2. `invoice_edits.old_value`/
# `new_value` son columnas TEXT (no bytea, spec del esquema original): para las filas sensibles se
# guarda `encode(pgp_sym_encrypt(valor, clave), 'base64')` en ese mismo TEXT, no una columna nueva.
SENSITIVE_EDIT_FIELDS = frozenset({"counterparty_tax_id", "counterparty_name"})


async def insert_edits(
    session: AsyncSession,
    *,
    invoice_id: UUID,
    company_id: UUID,
    edited_by: UUID,
    edits: list[Correction],
    encryption_key: str,
) -> None:
    """Inserta una fila por campo que cambió en una edición post-confirmación (S3.3, spec §2).

    Reutiliza `Correction` (mismo diff que `ocr_corrections`, `invoicing.corrections`): `ai_value`
    es aquí el valor ANTERIOR de la factura, `human_value` el editado (nombres del dataclass
    genéricos; las columnas de `invoice_edits` sí se llaman `old_value`/`new_value`, más precisas
    para este caso de uso humano-vs-humano). Un campo de `SENSITIVE_EDIT_FIELDS` (CIF/nombre de
    contraparte, spec S5.2 C7) se cifra; el resto se guarda en claro, igual que siempre.
    """
    for edit in edits:
        sensitive = edit.field in SENSITIVE_EDIT_FIELDS
        old_expr = (
            "encode(pgp_sym_encrypt(:old_value, :key), 'base64')" if sensitive else ":old_value"
        )
        new_expr = (
            "encode(pgp_sym_encrypt(:new_value, :key), 'base64')" if sensitive else ":new_value"
        )
        await session.execute(
            text(
                f"INSERT INTO invoice_edits "
                f"(tenant_id, company_id, invoice_id, field, old_value, new_value, edited_by) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :invoice_id, :field, {old_expr}, "
                f" {new_expr}, :edited_by)"
            ),
            {
                "company_id": str(company_id),
                "invoice_id": str(invoice_id),
                "field": edit.field,
                "old_value": edit.ai_value,
                "new_value": edit.human_value,
                "edited_by": str(edited_by),
                "key": encryption_key,
            },
        )


@dataclass(frozen=True)
class InvoiceEditEntry:
    """Una fila de `invoice_edits`: un campo que cambió en una edición.

    Se expone por primera vez (2026-08-01) vía `GET /invoices/{id}/history` — hasta ahora
    `invoice_edits` era solo escritura.
    """

    id: UUID
    field: str
    old_value: str | None
    new_value: str | None
    edited_by: UUID
    edited_at: datetime


async def list_edits(
    session: AsyncSession, invoice_id: UUID, *, encryption_key: str
) -> list[InvoiceEditEntry]:
    """Historial de ediciones de una factura del contexto, más reciente primero (2026-08-01).

    Mismo patrón que `companies.repository.list_company_edits`: descifra por fila según si `field`
    está en `SENSITIVE_EDIT_FIELDS` (CIF/nombre de contraparte, S5.2 C7).
    """
    sensitive = ", ".join(f"'{field}'" for field in sorted(SENSITIVE_EDIT_FIELDS))
    rows = (
        await session.execute(
            text(
                "SELECT id, field, "
                f"CASE WHEN field IN ({sensitive}) "
                "     THEN pgp_sym_decrypt(decode(old_value, 'base64'), :key)::text "
                "     ELSE old_value END AS old_value, "
                f"CASE WHEN field IN ({sensitive}) "
                "     THEN pgp_sym_decrypt(decode(new_value, 'base64'), :key)::text "
                "     ELSE new_value END AS new_value, "
                "edited_by, edited_at "
                "FROM invoice_edits WHERE invoice_id = :invoice_id ORDER BY edited_at DESC"
            ),
            {"invoice_id": str(invoice_id), "key": encryption_key},
        )
    ).all()
    return [
        InvoiceEditEntry(
            id=r.id,
            field=r.field,
            old_value=r.old_value,
            new_value=r.new_value,
            edited_by=r.edited_by,
            edited_at=r.edited_at,
        )
        for r in rows
    ]


async def list_history(
    session: AsyncSession, *, uploaded_by: UUID | None = None,
    cursor_created_at: datetime | None = None, cursor_id: UUID | None = None,
    limit: int = HISTORY_LIMIT,
) -> HistoryPage:
    """Facturas confirmadas de los últimos cuatro meses, más recientes primero (R-056).

    La RLS acota el tenant. El usuario conserva además su frontera de propietario y el cursor usa la
    misma pareja fecha/id que inbox para no saltar ni duplicar filas.
    """
    rows = (
        await session.execute(
            text(
                "SELECT f.id, f.status, f.created_at, f.direction, i.invoice_number "
                "FROM uploaded_files f "
                "JOIN invoices i ON i.uploaded_file_id = f.id "
                "WHERE i.status = 'confirmed' "
                "AND f.created_at >= current_timestamp - interval '4 months' "
                "AND i.is_test = false "
                "AND ((:uploaded_by)::uuid IS NULL OR f.uploaded_by = (:uploaded_by)::uuid) "
                "AND (CAST(:cursor_created_at AS timestamptz) IS NULL OR "
                "     f.created_at < CAST(:cursor_created_at AS timestamptz) OR "
                "     (f.created_at = CAST(:cursor_created_at AS timestamptz) "
                "      AND f.id < CAST(:cursor_id AS uuid))) "
                "ORDER BY f.created_at DESC, f.id DESC "
                "LIMIT :limit"
            ),
            {
                "limit": limit + 1,
                "uploaded_by": str(uploaded_by) if uploaded_by is not None else None,
                "cursor_created_at": cursor_created_at,
                "cursor_id": str(cursor_id) if cursor_id is not None else None,
            },
        )
    ).all()
    entries = [
        HistoryEntry(
            id=row.id,
            status=row.status,
            created_at=row.created_at,
            direction=row.direction,
            invoice_number=row.invoice_number,
        )
        for row in rows
    ]
    return HistoryPage(entries=entries[:limit], has_more=len(entries) > limit)


async def list_inbox(
    session: AsyncSession,
    *,
    uploaded_by: UUID,
    limit: int,
    cursor_created_at: datetime | None = None,
    cursor_id: UUID | None = None,
) -> InboxPage:
    """Lista la bandeja SELF ONLY con cursor compuesto y resumen agregado (R-020).

    `capture_unreadable` (S6.14: la imagen en sí es el problema, ni se ha llegado a leer) queda
    fuera tanto del listado como del resumen `attention` (paso 9, ajustes UI): no es "pendiente de
    comprobación", es una captura que hay que repetir. Su limpieza/expiración no necesita un job
    nuevo: `jobs.retention.purge_expired_unconfirmed_documents` (R-028) ya purga cualquier
    `uploaded_file` con `status <> 'confirmed'` (incluido este) a los 90 días.
    """
    rows = (
        await session.execute(
            text(
                "SELECT f.id, f.status, f.processing_stage, f.created_at, f.direction, "
                "       f.capture_session_id, f.capture_sequence, "
                "       1 + (SELECT count(*) FROM uploaded_file_pages p "
                "            WHERE p.root_uploaded_file_id = f.id) AS page_count "
                "FROM uploaded_files f "
                "WHERE f.uploaded_by = :uploaded_by "
                "  AND f.status != 'capture_unreadable' "
                "  AND NOT EXISTS (SELECT 1 FROM invoices i "
                "                  WHERE i.uploaded_file_id = f.id) "
                "  AND (CAST(:cursor_created_at AS timestamptz) IS NULL OR "
                "       f.created_at < CAST(:cursor_created_at AS timestamptz) OR "
                "       (f.created_at = CAST(:cursor_created_at AS timestamptz) "
                "        AND f.id < CAST(:cursor_id AS uuid))) "
                "ORDER BY f.created_at DESC, f.id DESC LIMIT :limit"
            ),
            {
                "uploaded_by": str(uploaded_by),
                "cursor_created_at": cursor_created_at,
                "cursor_id": str(cursor_id) if cursor_id is not None else None,
                "limit": limit + 1,
            },
        )
    ).all()
    summary_row = (
        await session.execute(
            text(
                "SELECT count(*) FILTER (WHERE f.status IN "
                "                    ('pending_ocr', 'processing')) AS processing, "
                "       count(*) FILTER (WHERE f.status IN ('ocr_done', 'confirmed')) AS ready, "
                "       count(*) FILTER (WHERE f.status IN "
                "                    ('needs_review', 'ocr_failed')) "
                "                    AS attention "
                "FROM uploaded_files f "
                "WHERE f.uploaded_by = :uploaded_by "
                "  AND f.status != 'capture_unreadable' "
                "  AND NOT EXISTS (SELECT 1 FROM invoices i "
                "                  WHERE i.uploaded_file_id = f.id)"
            ),
            {"uploaded_by": str(uploaded_by)},
        )
    ).one()
    return InboxPage(
        items=[
            InboxEntry(
                id=row.id,
                status=row.status,
                processing_stage=row.processing_stage,
                created_at=row.created_at,
                direction=row.direction,
                page_count=row.page_count,
                capture_session_id=row.capture_session_id,
                capture_sequence=row.capture_sequence,
            )
            for row in rows[:limit]
        ],
        summary=InboxSummary(
            processing=summary_row.processing,
            ready=summary_row.ready,
            attention=summary_row.attention,
        ),
        has_more=len(rows) > limit,
    )


async def list_supervision(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    limit: int,
    cursor_created_at: datetime | None = None,
    cursor_id: UUID | None = None,
    encryption_key: str,
) -> SupervisionPage:
    """Lista pendientes de otros usuarios del tenant para `tenant_admin` (R-026)."""
    rows = (
        await session.execute(
            text(
                "SELECT f.id, u.email AS user_email, "
                "       pgp_sym_decrypt(c.name, :key)::text AS company_name, "
                "       f.status, f.created_at, f.direction, "
                "       1 + (SELECT count(*) FROM uploaded_file_pages p "
                "            WHERE p.root_uploaded_file_id = f.id) AS page_count "
                "FROM uploaded_files f "
                "JOIN users u ON u.id = f.uploaded_by "
                "JOIN companies c ON c.id = f.company_id "
                "WHERE f.uploaded_by <> :actor_user_id "
                "  AND f.status <> 'confirmed' "
                "  AND NOT EXISTS (SELECT 1 FROM invoices i "
                "                  WHERE i.uploaded_file_id = f.id AND i.is_test = true) "
                "  AND (CAST(:cursor_created_at AS timestamptz) IS NULL OR "
                "       f.created_at < CAST(:cursor_created_at AS timestamptz) OR "
                "       (f.created_at = CAST(:cursor_created_at AS timestamptz) "
                "        AND f.id < CAST(:cursor_id AS uuid))) "
                "ORDER BY f.created_at DESC, f.id DESC LIMIT :limit"
            ),
            {
                "actor_user_id": str(actor_user_id),
                "key": encryption_key,
                "cursor_created_at": cursor_created_at,
                "cursor_id": str(cursor_id) if cursor_id is not None else None,
                "limit": limit + 1,
            },
        )
    ).all()
    return SupervisionPage(
        items=[
            SupervisionEntry(
                id=row.id,
                user_email=row.user_email,
                company_name=row.company_name,
                status=row.status,
                created_at=row.created_at,
                direction=row.direction,
                page_count=row.page_count,
            )
            for row in rows[:limit]
        ],
        has_more=len(rows) > limit,
    )
