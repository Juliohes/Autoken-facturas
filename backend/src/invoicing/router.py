"""Endpoints HTTP de la persistencia de facturas (S2.5): review (GET) y confirm (POST).

Capa HTTP **fina**: autentica y autoriza (portero de roles; la pertenencia fina la comprueba el
servicio), tipa el body y traduce el resultado o la excepción de dominio de `invoicing.service` a la
respuesta HTTP. No contiene SQL ni reglas de negocio.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from identity.authz import require_roles
from identity.dependencies import AuthContext
from invoicing import service
from tenancy.constants import Role

router = APIRouter(prefix="/uploads", tags=["invoicing"])

# Historial de facturas (S2.6): mismo prefijo de recurso `invoices`, router aparte porque
# `router` ya lleva el prefijo `/uploads` (una `APIRouter` tiene un único prefijo).
history_router = APIRouter(prefix="/invoices", tags=["invoicing"])

# Identidad autorizada a revisar/confirmar: empleado (`user`) o admin de asesoría (`tenant_admin`).
# La pertenencia fina a la empresa del fichero la comprueba el servicio (403 vs 404, C10/C13).
Reviewer = Annotated[AuthContext, Depends(require_roles(Role.USER, Role.TENANT_ADMIN))]

# Mismo conjunto de roles que `Reviewer` (S2.6 no añade un rol nuevo), con su propio nombre: ver el
# historial no "revisa" un fichero, así que el gate se nombra por lo que autoriza aquí.
HistoryViewer = Reviewer


class TaxLineIn(BaseModel):
    """Un tramo de IVA confirmado del body de `confirm`."""

    iva_pct: Decimal | None = None
    base: Decimal | None = None
    cuota: Decimal | None = None


class ConfirmIn(BaseModel):
    """Cuerpo de la confirmación (S2.5): datos confirmados por el humano."""

    # `direction` acotada al enum de dominio (ADR-0006): fuera de {recibida, emitida} -> 422.
    direction: Literal["recibida", "emitida"]
    issue_date: date | None = None
    counterparty_tax_id: str | None = None
    counterparty_name: str | None = None
    net_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    irpf_amount: Decimal | None = None
    tax_lines: list[TaxLineIn] = []
    responsibility_accepted: bool = False
    is_test: bool = False


# Traducción única de cada excepción de dominio a su código HTTP (spec §3).
_ERROR_STATUS: list[tuple[type[Exception], int, str]] = [
    (service.CompanyForbidden, 403, "No perteneces a la empresa del fichero"),
    (service.FileNotVisible, 404, "Fichero no encontrado"),
    (service.AlreadyConfirmed, 409, "El fichero ya tiene una factura confirmada"),
    (service.NotConfirmable, 409, "El fichero no tiene datos de revisión que confirmar"),
    (service.CounterpartyBlocked, 422, "El CIF de contraparte no es válido o no consta"),
    (service.OwnTaxIdMissing, 422, "El CIF propio no aparece en la factura"),
    (service.ResponsibilityNotAccepted, 422, "Debes aceptar la responsabilidad para confirmar"),
]


def _raise_http(exc: service.InvoicingError) -> NoReturn:
    """Traduce una excepción de dominio al `HTTPException` correspondiente (o la propaga)."""
    for error_type, status, detail in _ERROR_STATUS:
        if isinstance(exc, error_type):
            raise HTTPException(status_code=status, detail=detail) from exc
    raise exc  # pragma: no cover - toda subclase de dominio está mapeada arriba


@router.get("/{file_id}/review")
async def review_upload(identity: Reviewer, file_id: UUID) -> dict[str, object]:
    """Datos de revisión de un fichero ya leído (S2.4). 200 con datos; 403/404/409 por acceso."""
    try:
        data = await service.review(identity, file_id)
    except service.InvoicingError as exc:
        _raise_http(exc)
    return {
        "fields": data.fields,
        "confidences": data.confidences,
        "counterparty_verdict": data.counterparty_verdict,
        "own": data.own,
        "warnings": data.warnings,
        "blocking_reasons": data.blocking_reasons,
    }


@router.post("/{file_id}/confirm", status_code=201)
async def confirm_upload(identity: Reviewer, file_id: UUID, body: ConfirmIn) -> dict[str, object]:
    """Confirma un fichero y persiste su factura (S2.5). 201 con el id; 4xx según las guardas."""
    command = service.ConfirmCommand(
        direction=body.direction,
        issue_date=body.issue_date,
        counterparty_tax_id=body.counterparty_tax_id,
        counterparty_name=body.counterparty_name,
        net_amount=body.net_amount,
        tax_amount=body.tax_amount,
        total_amount=body.total_amount,
        irpf_amount=body.irpf_amount,
        tax_lines=[
            service.ConfirmTaxLine(iva_pct=line.iva_pct, base=line.base, cuota=line.cuota)
            for line in body.tax_lines
        ],
        responsibility_accepted=body.responsibility_accepted,
        is_test=body.is_test,
    )
    try:
        invoice_id = await service.confirm(identity, file_id, command)
    except service.InvoicingError as exc:
        _raise_http(exc)
    return {"id": str(invoice_id)}


class HistoryEntryOut(BaseModel):
    """Una entrada del historial de facturas confirmadas (S2.6, spec §2)."""

    id: UUID
    issue_date: date | None
    direction: str
    counterparty_tax_id: str | None
    counterparty_name: str | None
    counterparty_cif_status: str
    total_amount: Decimal | None
    confirmed_at: datetime


class HistoryOut(BaseModel):
    """Respuesta de `GET /invoices/history`: lista, más reciente primero (spec §2/§3)."""

    entries: list[HistoryEntryOut]


@history_router.get("/history")
async def invoice_history(identity: HistoryViewer) -> HistoryOut:
    """Facturas confirmadas de los últimos 7 días del contexto del usuario (S2.6). Solo lectura."""
    entries = await service.history(identity)
    return HistoryOut(
        entries=[
            HistoryEntryOut(
                id=entry.id,
                issue_date=entry.issue_date,
                direction=entry.direction,
                counterparty_tax_id=entry.counterparty_tax_id,
                counterparty_name=entry.counterparty_name,
                counterparty_cif_status=entry.counterparty_cif_status,
                total_amount=entry.total_amount,
                confirmed_at=entry.confirmed_at,
            )
            for entry in entries
        ]
    )
