"""Casos de uso de borradores de revisión (R-021/R-022)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from time import perf_counter
from uuid import UUID

from identity.dependencies import AuthContext
from invoice_intake import service as intake_service
from invoicing import draft_repository
from shared.config import get_settings
from shared.encryption import tenant_encryption_key, tenant_tax_id_blind_index
from shared.metrics import draft_save_failures, draft_save_latency_seconds


class DraftError(Exception):
    """Error de dominio de un borrador."""


class DraftFileForbidden(DraftError):
    """El fichero pertenece a otra empresa del tenant."""


class DraftFileNotVisible(DraftError):
    """El fichero no pertenece al usuario o no existe."""


class DraftRevisionConflict(DraftError):
    def __init__(self, current_revision: int) -> None:
        self.current_revision = current_revision


@dataclass(frozen=True)
class DraftCommand:
    revision: int
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


@dataclass(frozen=True)
class DraftSave:
    revision: int
    updated_at: datetime


async def save(identity: AuthContext, file_id: UUID, command: DraftCommand) -> DraftSave:
    """Autoriza el fichero y guarda el snapshot solo si la revisión sigue vigente."""
    try:
        file_ctx = await intake_service.authorize_file_edit(
            identity.session,
            tenant_id=identity.tenant_id,
            file_id=file_id,
            actor_user_id=identity.user_id,
            actor_role=identity.role,
        )
    except intake_service.FileForbidden as exc:
        raise DraftFileForbidden from exc
    except (intake_service.FileNotVisible, intake_service.PrivateFileNotVisible) as exc:
        raise DraftFileNotVisible from exc

    started = perf_counter()
    try:
        result = await draft_repository.save(
            identity.session,
            uploaded_file_id=file_id,
            company_id=file_ctx.company_id,
            owner_user_id=identity.user_id,
            expected_revision=command.revision,
            direction=command.direction,
            issue_date=command.issue_date,
            invoice_number=command.invoice_number,
            counterparty_tax_id=command.counterparty_tax_id,
            counterparty_tax_id_blind_index=tenant_tax_id_blind_index(
                get_settings(), identity.tenant_id, command.counterparty_tax_id
            ),
            counterparty_name=command.counterparty_name,
            net_amount=command.net_amount,
            tax_amount=command.tax_amount,
            total_amount=command.total_amount,
            irpf_amount=command.irpf_amount,
            tax_lines=command.tax_lines,
            encryption_key=tenant_encryption_key(get_settings(), identity.tenant_id),
        )
    except Exception:
        draft_save_failures.inc()
        raise
    finally:
        draft_save_latency_seconds.observe(perf_counter() - started)
    if result.revision is None or result.updated_at is None:
        raise DraftRevisionConflict(result.current_revision or 0)
    return DraftSave(revision=result.revision, updated_at=result.updated_at)
