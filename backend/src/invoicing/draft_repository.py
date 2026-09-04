"""Persistencia de borradores de revisión (R-021), separada de las facturas confirmadas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


@dataclass(frozen=True)
class DraftSaveResult:
    revision: int | None
    updated_at: datetime | None
    current_revision: int | None = None


@dataclass(frozen=True)
class DraftRecord:
    direction: str | None
    issue_date: date | None
    invoice_number: str | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    net_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    irpf_amount: Decimal | None
    tax_lines: list[dict[str, str | None]]
    revision: int
    updated_at: datetime


async def get(
    session: AsyncSession, *, uploaded_file_id: UUID, encryption_key: str
) -> DraftRecord | None:
    """Lee un borrador visible y descifra solo sus campos identificativos."""
    row = (
        await session.execute(
            text(
                "SELECT direction, issue_date, invoice_number, "
                "pgp_sym_decrypt(counterparty_tax_id, :key)::text AS counterparty_tax_id, "
                "pgp_sym_decrypt(counterparty_name, :key)::text AS counterparty_name, "
                "net_amount, tax_amount, total_amount, irpf_amount, tax_lines, revision, "
                "updated_at "
                "FROM review_drafts WHERE uploaded_file_id = :uploaded_file_id"
            ),
            {"uploaded_file_id": str(uploaded_file_id), "key": encryption_key},
        )
    ).one_or_none()
    if row is None:
        return None
    tax_lines = row.tax_lines
    if isinstance(tax_lines, str):
        tax_lines = json.loads(tax_lines)
    return DraftRecord(
        direction=row.direction,
        issue_date=row.issue_date,
        invoice_number=row.invoice_number,
        counterparty_tax_id=row.counterparty_tax_id,
        counterparty_name=row.counterparty_name,
        net_amount=row.net_amount,
        tax_amount=row.tax_amount,
        total_amount=row.total_amount,
        irpf_amount=row.irpf_amount,
        tax_lines=tax_lines,
        revision=row.revision,
        updated_at=row.updated_at,
    )


async def delete(session: AsyncSession, *, uploaded_file_id: UUID) -> None:
    """Elimina el borrador en la misma transacción que la confirmación."""
    await session.execute(
        text("DELETE FROM review_drafts WHERE uploaded_file_id = :uploaded_file_id"),
        {"uploaded_file_id": str(uploaded_file_id)},
    )


async def save(
    session: AsyncSession,
    *,
    uploaded_file_id: UUID,
    company_id: UUID,
    owner_user_id: UUID,
    expected_revision: int,
    direction: str | None,
    issue_date: date | None,
    invoice_number: str | None,
    counterparty_tax_id: str | None,
    counterparty_tax_id_blind_index: str | None,
    counterparty_name: str | None,
    net_amount: Decimal | None,
    tax_amount: Decimal | None,
    total_amount: Decimal | None,
    irpf_amount: Decimal | None,
    tax_lines: list[dict[str, str | None]],
    encryption_key: str,
) -> DraftSaveResult:
    """Guarda si la revisión coincide y devuelve la revisión siguiente."""
    params = {
        "uploaded_file_id": str(uploaded_file_id),
        "company_id": str(company_id),
        "owner_user_id": str(owner_user_id),
        "expected_revision": expected_revision,
        "direction": direction,
        "issue_date": issue_date,
        "invoice_number": invoice_number,
        "counterparty_tax_id": counterparty_tax_id,
        "counterparty_tax_id_blind_index": counterparty_tax_id_blind_index,
        "counterparty_name": counterparty_name,
        "net_amount": net_amount,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
        "irpf_amount": irpf_amount,
        "tax_lines": json.dumps(tax_lines),
        "key": encryption_key,
    }
    updated = (
        await session.execute(
            text(
                "UPDATE review_drafts SET "
                "direction = :direction, issue_date = :issue_date, "
                "invoice_number = :invoice_number, "
                "counterparty_tax_id = pgp_sym_encrypt(:counterparty_tax_id, :key), "
                "counterparty_tax_id_blind_index = :counterparty_tax_id_blind_index, "
                "counterparty_name = pgp_sym_encrypt(:counterparty_name, :key), "
                "net_amount = :net_amount, tax_amount = :tax_amount, total_amount = :total_amount, "
                "irpf_amount = :irpf_amount, tax_lines = CAST(:tax_lines AS jsonb), "
                "revision = revision + 1, updated_at = now() "
                "WHERE uploaded_file_id = :uploaded_file_id AND revision = :expected_revision "
                "RETURNING revision, updated_at"
            ),
            params,
        )
    ).one_or_none()
    if updated is not None:
        return DraftSaveResult(revision=updated.revision, updated_at=updated.updated_at)

    if expected_revision == 0:
        inserted = (
            await session.execute(
                text(
                    "INSERT INTO review_drafts (uploaded_file_id, tenant_id, company_id, "
                    "owner_user_id, "
                    "direction, issue_date, invoice_number, counterparty_tax_id, "
                    "counterparty_tax_id_blind_index, counterparty_name, net_amount, tax_amount, "
                    "total_amount, irpf_amount, tax_lines, revision) "
                    "VALUES (:uploaded_file_id, "
                    f"{_TENANT_FROM_CONTEXT}, :company_id, :owner_user_id, "
                    ":direction, :issue_date, "
                    ":invoice_number, pgp_sym_encrypt(:counterparty_tax_id, :key), "
                    ":counterparty_tax_id_blind_index, pgp_sym_encrypt(:counterparty_name, :key), "
                    ":net_amount, :tax_amount, :total_amount, :irpf_amount, "
                    "CAST(:tax_lines AS jsonb), 1) "
                    "ON CONFLICT (uploaded_file_id) DO NOTHING "
                    "RETURNING revision, updated_at"
                ),
                params,
            )
        ).one_or_none()
        if inserted is not None:
            return DraftSaveResult(revision=inserted.revision, updated_at=inserted.updated_at)

    current = await session.execute(
        text("SELECT revision FROM review_drafts WHERE uploaded_file_id = :uploaded_file_id"),
        {"uploaded_file_id": str(uploaded_file_id)},
    )
    row = current.one_or_none()
    return DraftSaveResult(
        revision=None,
        updated_at=None,
        current_revision=row.revision if row is not None else 0,
    )
