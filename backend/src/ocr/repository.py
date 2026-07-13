"""Acceso a datos de la extracción OCR (S2.3): SQL de `ocr_extractions` (upsert idempotente).

La sesión llega ya abierta en el contexto de aislamiento del tenant (S1.1): la RLS de dos niveles
decide qué filas se ven y se escriben. El `tenant_id` de la escritura NO viaja por parámetro: sale
de `app.tenant_id` (la misma fuente que la RLS), de modo que ninguna fila cruce el tenant de la
petición. El upsert por `uploaded_file_id` (UNIQUE) garantiza una extracción vigente por fichero
(idempotencia): reprocesar reemplaza, no duplica.

El SQL de `uploaded_files` (ubicación + transición de estado) NO vive aquí: es dominio de
`invoice_intake` (`invoice_intake.repository`), que el job invoca. Esta capa solo escribe la
extracción; no toca la máquina de estados del fichero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# `tenant_id` de la escritura derivado del contexto de la sesión (coherente con la RLS).
_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# Upsert idempotente por `uploaded_file_id`: una extracción vigente por fichero (C10). Al reprocesar
# se reemplazan los campos y se refresca `updated_at`; `created_at` es INMUTABLE (marca la primera
# extracción del fichero, no la del último reproceso), por eso queda FUERA del `DO UPDATE`.
_UPSERT = text(
    f"INSERT INTO ocr_extractions "
    f"(tenant_id, company_id, uploaded_file_id, issue_date, total_amount, net_amount, tax_amount, "
    f" tax_lines, counterparty_tax_id, counterparty_name, own_tax_id_present, confidences, "
    f" validations, engine, model, raw, status) "
    f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :uploaded_file_id, :issue_date, :total_amount, "
    f" :net_amount, :tax_amount, CAST(:tax_lines AS jsonb), :counterparty_tax_id, "
    f" :counterparty_name, :own_tax_id_present, CAST(:confidences AS jsonb), "
    f" CAST(:validations AS jsonb), :engine, :model, CAST(:raw AS jsonb), :status) "
    f"ON CONFLICT (uploaded_file_id) DO UPDATE SET "
    f" issue_date = EXCLUDED.issue_date, total_amount = EXCLUDED.total_amount, "
    f" net_amount = EXCLUDED.net_amount, tax_amount = EXCLUDED.tax_amount, "
    f" tax_lines = EXCLUDED.tax_lines, counterparty_tax_id = EXCLUDED.counterparty_tax_id, "
    f" counterparty_name = EXCLUDED.counterparty_name, "
    f" own_tax_id_present = EXCLUDED.own_tax_id_present, confidences = EXCLUDED.confidences, "
    f" validations = EXCLUDED.validations, engine = EXCLUDED.engine, model = EXCLUDED.model, "
    f" raw = EXCLUDED.raw, status = EXCLUDED.status, updated_at = now()"
)


@dataclass(frozen=True)
class ExtractionRecord:
    """Extracción OCR vigente de un fichero (S2.3): baseline de la revisión y del diff.

    `tax_lines` conserva el formato persistido por el worker (`[{base, rate, cuota}]`). Los
    importes son `Decimal` (o `None` si el campo no se leyó, regla anti-alucinación).
    """

    issue_date: date | None
    total_amount: Decimal | None
    net_amount: Decimal | None
    tax_amount: Decimal | None
    tax_lines: list[dict[str, Any]]
    counterparty_tax_id: str | None
    counterparty_name: str | None
    own_tax_id_present: bool
    confidences: dict[str, Any]
    status: str


async def get_extraction(session: AsyncSession, uploaded_file_id: UUID) -> ExtractionRecord | None:
    """Lee la extracción vigente de un fichero en el contexto (RLS), o `None` si no hay.

    La usan la pantalla de revisión (S2.4) y la confirmación (S2.5): el baseline del OCR (S2.3) para
    pintar los campos con su confianza y para el diff de `ocr_corrections` (campos que el humano
    cambió respecto a lo que leyó la IA).
    """
    row = (
        await session.execute(
            text(
                "SELECT issue_date, total_amount, net_amount, tax_amount, tax_lines, "
                "counterparty_tax_id, counterparty_name, own_tax_id_present, confidences, status "
                "FROM ocr_extractions WHERE uploaded_file_id = :fid"
            ),
            {"fid": str(uploaded_file_id)},
        )
    ).first()
    if row is None:
        return None
    return ExtractionRecord(
        issue_date=row.issue_date,
        total_amount=row.total_amount,
        net_amount=row.net_amount,
        tax_amount=row.tax_amount,
        tax_lines=list(row.tax_lines),
        counterparty_tax_id=row.counterparty_tax_id,
        counterparty_name=row.counterparty_name,
        own_tax_id_present=row.own_tax_id_present,
        confidences=dict(row.confidences),
        status=row.status,
    )


async def upsert_extraction(
    session: AsyncSession,
    *,
    company_id: UUID,
    uploaded_file_id: UUID,
    issue_date: date | None,
    total_amount: Decimal | None,
    net_amount: Decimal | None,
    tax_amount: Decimal | None,
    tax_lines: list[dict[str, Any]],
    counterparty_tax_id: str | None,
    counterparty_name: str | None,
    own_tax_id_present: bool,
    confidences: dict[str, Any],
    validations: dict[str, Any],
    engine: str,
    model: str,
    raw: dict[str, Any],
    status: str,
) -> None:
    """Inserta o reemplaza la extracción del fichero en el tenant del contexto (idempotente)."""
    await session.execute(
        _UPSERT,
        {
            "company_id": str(company_id),
            "uploaded_file_id": str(uploaded_file_id),
            "issue_date": issue_date,
            "total_amount": total_amount,
            "net_amount": net_amount,
            "tax_amount": tax_amount,
            "tax_lines": json.dumps(tax_lines),
            "counterparty_tax_id": counterparty_tax_id,
            "counterparty_name": counterparty_name,
            "own_tax_id_present": own_tax_id_present,
            "confidences": json.dumps(confidences),
            "validations": json.dumps(validations),
            "engine": engine,
            "model": model,
            "raw": json.dumps(raw),
            "status": status,
        },
    )
