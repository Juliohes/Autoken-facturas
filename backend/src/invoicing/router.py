"""Endpoints HTTP de la persistencia de facturas: review/confirm (S2.5), historial (S2.6), edición
auditada (S3.3) y purga de facturas de prueba (S3.5).

Capa HTTP **fina**: autentica y autoriza (portero de roles; la pertenencia fina la comprueba el
servicio), tipa el body y traduce el resultado o la excepción de dominio de `invoicing.service` a la
respuesta HTTP. No contiene SQL ni reglas de negocio.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, NoReturn, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from identity.authz import require_roles
from identity.dependencies import AuthContext
from identity.ratelimit import draft_counterparty_attempt_exceeds
from invoicing import draft_service, service
from shared.config import get_settings
from shared.redis import get_redis
from shared.rollout import FeatureFlag, is_rollout_enabled
from tenancy.constants import Role

router = APIRouter(prefix="/uploads", tags=["invoicing"])

# Historial (S2.6) y edición (S3.3): mismo prefijo de recurso `invoices`, router aparte porque
# `router` ya lleva el prefijo `/uploads` (una `APIRouter` tiene un único prefijo).
invoices_router = APIRouter(prefix="/invoices", tags=["invoicing"])

# Identidad autorizada a revisar/confirmar: empleado (`user`) o admin de asesoría (`tenant_admin`).
# La pertenencia fina a la empresa del fichero la comprueba el servicio (403 vs 404, C10/C13).
Reviewer = Annotated[AuthContext, Depends(require_roles(Role.USER, Role.TENANT_ADMIN))]

# Mismo conjunto de roles que `Reviewer` (S2.6 no añade un rol nuevo), con su propio nombre: ver el
# historial no "revisa" un fichero, así que el gate se nombra por lo que autoriza aquí.
HistoryViewer = Reviewer

# Supervisión de pendientes: solo `tenant_admin`, y la apertura usa un endpoint distinto del review
# editable para no convertir un parámetro `readonly=true` en una falsa frontera de seguridad.
Supervisor = Annotated[AuthContext, Depends(require_roles(Role.TENANT_ADMIN))]

# Editar una factura ya confirmada es exclusivo de `tenant_admin` (spec S3.3, decisión de dominio
# 1): a diferencia de `Reviewer`, el empleado no entra aquí.
InvoiceEditor = Annotated[AuthContext, Depends(require_roles(Role.TENANT_ADMIN))]


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
    invoice_number: str | None = None
    net_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    irpf_amount: Decimal | None = None
    tax_lines: list[TaxLineIn] = []
    responsibility_accepted: bool = False
    own_tax_id_exception_accepted: bool = False
    is_test: bool = False


class DraftCounterpartyVerdictIn(BaseModel):
    """Valores actuales del formulario para validar antes de confirmar (S6.10)."""

    counterparty_tax_id: str | None = None
    counterparty_name: str | None = None


class CounterpartyVerdictOut(BaseModel):
    status: Literal["valid", "invalid", "not_found", "unverified"]
    name_match: bool | None
    official_name: str | None


class DraftCounterpartyVerdictOut(BaseModel):
    counterparty_verdict: CounterpartyVerdictOut
    blocking_reasons: list[str]


class ReviewDraftIn(BaseModel):
    """Snapshot editable previo a confirmar una factura (R-022)."""

    revision: int = Field(ge=0)
    direction: Literal["recibida", "emitida"] | None = None
    issue_date: date | None = None
    invoice_number: str | None = None
    counterparty_tax_id: str | None = None
    counterparty_name: str | None = None
    net_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    irpf_amount: Decimal | None = None
    tax_lines: list[TaxLineIn] = Field(default_factory=list)


class ReviewDraftOut(BaseModel):
    revision: int
    updated_at: datetime


# Traducción única de cada excepción de dominio a su código HTTP (spec §3).
_ERROR_STATUS: list[tuple[type[Exception], int, str]] = [
    (service.CompanyForbidden, 403, "No perteneces a la empresa del fichero"),
    (service.FileNotVisible, 404, "Fichero no encontrado"),
    (service.AlreadyConfirmed, 409, "El fichero ya tiene una factura confirmada"),
    # `PendingOcr`/`CaptureUnreadable` antes que `NotConfirmable`: son sus subclases, y
    # `_raise_http` usa el PRIMER match — si `NotConfirmable` fuera antes, nunca se alcanzarían.
    (service.PendingOcr, 409, "La factura todavía se está procesando con IA"),
    # Contrato literal EXACTO compartido con el frontend (S6.14): no cambiar este texto sin
    # coordinarlo, el cliente lo usa para decidir si redirige a repetir la captura.
    (service.CaptureUnreadable, 409, "La foto no se pudo leer, repite la captura"),
    (service.NotConfirmable, 409, "El fichero no tiene datos de revisión que confirmar"),
    (service.CounterpartyBlocked, 422, "El CIF de contraparte no es válido o no consta"),
    (service.OwnTaxIdMissing, 422, "El CIF propio no aparece en la factura"),
    (service.ResponsibilityNotAccepted, 422, "Debes aceptar la responsabilidad para confirmar"),
    (service.InvoiceNotVisible, 404, "Factura no encontrada"),
    (
        service.CounterpartyNameRequired,
        422,
        "Si cambias el CIF de contraparte, indica también su nombre",
    ),
]


def _raise_http(exc: service.InvoicingError) -> NoReturn:
    """Traduce una excepción de dominio al `HTTPException` correspondiente (o la propaga)."""
    for error_type, status, detail in _ERROR_STATUS:
        if isinstance(exc, error_type):
            structured_detail = (
                exc.as_detail() if isinstance(exc, service.StructuredInvoicingError) else detail
            )
            raise HTTPException(status_code=status, detail=structured_detail) from exc
    raise exc  # pragma: no cover - toda subclase de dominio está mapeada arriba


@router.put("/{file_id}/draft", response_model=ReviewDraftOut)
async def save_review_draft(
    identity: Reviewer, file_id: UUID, body: ReviewDraftIn
) -> ReviewDraftOut:
    """Guarda un borrador con control optimista de revisión (R-022)."""
    if not is_rollout_enabled(get_settings(), FeatureFlag.DRAFT_AUTOSAVE, identity.tenant_id):
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    try:
        result = await draft_service.save(
            identity,
            file_id,
            draft_service.DraftCommand(
                revision=body.revision,
                direction=body.direction,
                issue_date=body.issue_date,
                invoice_number=body.invoice_number,
                counterparty_tax_id=body.counterparty_tax_id,
                counterparty_name=body.counterparty_name,
                net_amount=body.net_amount,
                tax_amount=body.tax_amount,
                total_amount=body.total_amount,
                irpf_amount=body.irpf_amount,
                tax_lines=[
                    {
                        "iva_pct": str(line.iva_pct) if line.iva_pct is not None else None,
                        "base": str(line.base) if line.base is not None else None,
                        "cuota": str(line.cuota) if line.cuota is not None else None,
                    }
                    for line in body.tax_lines
                ],
            ),
        )
    except draft_service.DraftFileForbidden as exc:
        raise HTTPException(
            status_code=403, detail="No perteneces a la empresa del fichero"
        ) from exc
    except draft_service.DraftFileNotVisible as exc:
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except draft_service.DraftRevisionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "draft_revision_conflict", "current_revision": exc.current_revision},
        ) from exc
    return ReviewDraftOut(revision=result.revision, updated_at=result.updated_at)


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
        "direction": data.direction,
        "source": data.source,
        "draft_revision": data.draft_revision,
        "draft_updated_at": data.draft_updated_at,
        "page_count": data.page_count,
    }


@router.post("/{file_id}/counterparty-verdict", response_model=DraftCounterpartyVerdictOut)
async def draft_counterparty_verdict(
    identity: Reviewer, file_id: UUID, body: DraftCounterpartyVerdictIn
) -> dict[str, object]:
    """Valida el CIF/nombre que se está editando, sin guardar una factura (S6.10 C6)."""
    # El endpoint consulta verificadores externos: limita el tecleo automatizado por usuario+tenant
    # sin penalizar el trabajo normal de corrección humana.
    if await draft_counterparty_attempt_exceeds(
        get_redis(),
        str(identity.tenant_id),
        str(identity.user_id),
        max_attempts=30,
        window_seconds=60,
    ):
        raise HTTPException(
            status_code=429, detail="Demasiadas comprobaciones de CIF. Espera un minuto."
        )
    try:
        data = await service.draft_counterparty_verdict(
            identity, file_id, body.counterparty_tax_id, body.counterparty_name
        )
    except service.InvoicingError as exc:
        _raise_http(exc)
    return {
        "counterparty_verdict": data.counterparty_verdict,
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
        invoice_number=body.invoice_number,
        net_amount=body.net_amount,
        tax_amount=body.tax_amount,
        total_amount=body.total_amount,
        irpf_amount=body.irpf_amount,
        tax_lines=[
            service.ConfirmTaxLine(iva_pct=line.iva_pct, base=line.base, cuota=line.cuota)
            for line in body.tax_lines
        ],
        responsibility_accepted=body.responsibility_accepted,
        own_tax_id_exception_accepted=body.own_tax_id_exception_accepted,
        is_test=body.is_test,
    )
    try:
        invoice_id = await service.confirm(identity, file_id, command)
    except service.InvoicingError as exc:
        _raise_http(exc)
    return {"id": str(invoice_id)}


class HistoryEntryOut(BaseModel):
    """Una entrada privada de historial, sin PII de contraparte (S6.12)."""

    id: UUID
    status: str
    created_at: datetime
    direction: Literal["recibida", "emitida"] | None


class HistoryOut(BaseModel):
    """Respuesta de `GET /invoices/history`: últimos envíos, más reciente primero."""

    entries: list[HistoryEntryOut]


class InboxItemOut(BaseModel):
    """Documento de la bandeja personal, sin PII fiscal (R-020)."""

    id: UUID
    status: str
    processing_stage: str | None
    created_at: datetime
    direction: Literal["recibida", "emitida"] | None
    page_count: int
    capture_session_id: UUID | None
    capture_sequence: int | None
    draft_updated_at: datetime | None


class InboxSummaryOut(BaseModel):
    processing: int
    ready: int
    attention: int


class InboxOut(BaseModel):
    items: list[InboxItemOut]
    summary: InboxSummaryOut
    next_cursor: str | None


class SupervisionItemOut(BaseModel):
    """Metadata de un pendiente ajeno para `tenant_admin`, sin acciones de escritura (R-026)."""

    id: UUID
    user_email: str
    company_name: str
    status: str
    created_at: datetime
    direction: Literal["recibida", "emitida"] | None
    page_count: int


class SupervisionOut(BaseModel):
    items: list[SupervisionItemOut]
    next_cursor: str | None


def _review_payload(data: service.ReviewData) -> dict[str, object]:
    return {
        "fields": data.fields,
        "confidences": data.confidences,
        "counterparty_verdict": data.counterparty_verdict,
        "own": data.own,
        "warnings": data.warnings,
        "blocking_reasons": data.blocking_reasons,
        "direction": data.direction,
        "source": data.source,
        "draft_revision": data.draft_revision,
        "draft_updated_at": data.draft_updated_at,
        "page_count": data.page_count,
    }


@invoices_router.get("/pending-supervision", response_model=SupervisionOut)
async def pending_supervision(
    identity: Supervisor,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = service.INBOX_LIMIT,
) -> SupervisionOut:
    """Pendientes de otros usuarios del tenant, solo metadata y paginación estable (R-026)."""
    try:
        data = await service.supervision(identity, cursor=cursor, limit=limit)
    except service.InvalidInboxCursor as exc:
        raise HTTPException(status_code=422, detail="Cursor de supervisión no válido") from exc
    return SupervisionOut(
        items=[
            SupervisionItemOut(
                id=item.id,
                user_email=item.user_email,
                company_name=item.company_name,
                status=item.status,
                created_at=item.created_at,
                direction=cast(Literal["recibida", "emitida"] | None, item.direction),
                page_count=item.page_count,
            )
            for item in data.items
        ],
        next_cursor=data.next_cursor,
    )


@invoices_router.get("/history")
async def invoice_history(identity: HistoryViewer) -> HistoryOut:
    """Últimos documentos aceptados del contexto del usuario (S6.12). Solo lectura."""
    entries = await service.history(identity)
    return HistoryOut(
        entries=[
            HistoryEntryOut(
                id=entry.id,
                status=entry.status,
                created_at=entry.created_at,
                direction=cast(Literal["recibida", "emitida"] | None, entry.direction),
            )
            for entry in entries
        ]
    )


@router.get("/{file_id}/review-readonly")
async def review_upload_readonly(identity: Supervisor, file_id: UUID) -> dict[str, object]:
    """Abre un pendiente ajeno para supervisión sin exponer acciones de escritura (R-026)."""
    try:
        data = await service.review(identity, file_id, readonly=True)
    except service.InvoicingError as exc:
        _raise_http(exc)
    return _review_payload(data)


@invoices_router.get("/inbox")
async def invoice_inbox(
    identity: HistoryViewer,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = service.INBOX_LIMIT,
) -> InboxOut:
    """Bandeja SELF ONLY, también para `tenant_admin`, con resumen y cursor estable."""
    if not is_rollout_enabled(get_settings(), FeatureFlag.REVIEW_INBOX, identity.tenant_id):
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    try:
        data = await service.inbox(identity, cursor=cursor, limit=limit)
    except service.InvalidInboxCursor as exc:
        raise HTTPException(status_code=422, detail="Cursor de bandeja no válido") from exc
    return InboxOut(
        items=[
            InboxItemOut(
                id=item.id,
                status=item.status,
                processing_stage=item.processing_stage,
                created_at=item.created_at,
                direction=cast(Literal["recibida", "emitida"] | None, item.direction),
                page_count=item.page_count,
                capture_session_id=item.capture_session_id,
                capture_sequence=item.capture_sequence,
                draft_updated_at=item.draft_updated_at,
            )
            for item in data.items
        ],
        summary=InboxSummaryOut(
            processing=data.summary.processing,
            ready=data.summary.ready,
            attention=data.summary.attention,
        ),
        next_cursor=data.next_cursor,
    )


class InvoiceEditIn(BaseModel):
    """Cuerpo de `PATCH /invoices/{id}` (S3.3): patch parcial, solo cambian los campos presentes."""

    issue_date: date | None = None
    counterparty_tax_id: str | None = None
    counterparty_name: str | None = None
    net_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    irpf_amount: Decimal | None = None
    tax_lines: list[TaxLineIn] | None = None


class InvoiceOut(BaseModel):
    """Estado de la factura tras la edición (spec S3.3 §2)."""

    id: UUID
    issue_date: date | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    counterparty_cif_status: str
    net_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    irpf_amount: Decimal | None
    balance_ok: bool | None


@invoices_router.patch("/{invoice_id}")
async def edit_invoice(
    identity: InvoiceEditor, invoice_id: UUID, body: InvoiceEditIn
) -> InvoiceOut:
    """Edita los campos presentes en el body de una factura confirmada. Solo `tenant_admin` (S3.3).

    Patch parcial real: solo las claves que el cliente envió (`model_fields_set`) llegan al
    servicio; un campo ausente en el body conserva su valor actual (spec §2). `tax_lines: null`
    explícito se trata como AUSENTE (no toca los tramos): solo una lista real (incluida `[]`, que
    los borra todos) es una instrucción de cambio; un `null` no es una lista de tramos válida.
    """
    patch: dict[str, object] = {}
    for field_name in body.model_fields_set:
        value = getattr(body, field_name)
        if field_name == "tax_lines":
            if value is None:
                continue
            value = [
                service.ConfirmTaxLine(iva_pct=line.iva_pct, base=line.base, cuota=line.cuota)
                for line in value
            ]
        patch[field_name] = value

    try:
        result = await service.edit_invoice(identity, invoice_id, patch)
    except service.InvoicingError as exc:
        _raise_http(exc)

    return InvoiceOut(
        id=result.id,
        issue_date=result.issue_date,
        counterparty_tax_id=result.counterparty_tax_id,
        counterparty_name=result.counterparty_name,
        counterparty_cif_status=result.counterparty_cif_status,
        net_amount=result.net_amount,
        tax_amount=result.tax_amount,
        total_amount=result.total_amount,
        irpf_amount=result.irpf_amount,
        balance_ok=result.balance_ok,
    )


class InvoiceEditEntryOut(BaseModel):
    """Una fila del historial de ediciones de una factura (2026-08-01)."""

    id: UUID
    field: str
    old_value: str | None
    new_value: str | None
    edited_by: UUID
    edited_at: datetime


@invoices_router.get("/{invoice_id}/history")
async def invoice_edit_history(
    identity: InvoiceEditor, invoice_id: UUID
) -> list[InvoiceEditEntryOut]:
    """Historial de ediciones de una factura, más reciente primero. De otro tenant -> 404."""
    try:
        entries = await service.invoice_history(identity, invoice_id)
    except service.InvoicingError as exc:
        _raise_http(exc)
    return [
        InvoiceEditEntryOut(
            id=e.id,
            field=e.field,
            old_value=e.old_value,
            new_value=e.new_value,
            edited_by=e.edited_by,
            edited_at=e.edited_at,
        )
        for e in entries
    ]


class PurgeResultOut(BaseModel):
    """Respuesta de `POST /invoices/test/purge` (S3.5): cuántas facturas de prueba se borraron."""

    purged: int


@invoices_router.post("/test/purge")
async def purge_test_invoices(identity: InvoiceEditor) -> PurgeResultOut:
    """Borra TODAS las facturas de prueba de la asesoría de una vez (S3.5). Solo `tenant_admin`."""
    result = await service.purge_test_invoices(identity)
    return PurgeResultOut(purged=result.purged)
