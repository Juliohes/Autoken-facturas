"""Lógica de dominio de la persistencia de facturas (S2.5): orquesta `review` y `confirm`.

El router HTTP es fino: traduce la petición a estas operaciones y sus excepciones de dominio a
códigos HTTP. Aquí viven las guardas de servidor (spec §4, "el servidor no confía en el cliente"):
reverifica el CIF de contraparte con S2.8, reimpone el CIF propio presente (salvo admin) y la
aceptación de responsabilidad, y se persiste TODO en la transacción de la petición (atomicidad):
factura + tramos + correcciones (diff vs OCR) + snapshot en `audit_log` + transición del fichero. El
descuadre aritmético AVISA pero no bloquea (regla 5).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from companies import repository as companies_repo
from companies.service import tenant_encryption_key as company_encryption_key
from counterparty.constants import CifStatus
from counterparty.service import CounterpartyVerdict, record_confirmation, verify_counterparty
from identity.dependencies import AuthContext
from invoice_intake import repository as intake_repo
from invoice_intake import service as intake_service
from invoice_intake.constants import FileStatus
from invoicing import draft_repository, repository, supplier_profile_repository
from invoicing.corrections import (
    BaselineFields,
    ConfirmedFields,
    Correction,
    TaxLineFields,
    diff_corrections,
)
from invoicing.supplier_profiles import build_profile_features, supplier_profile_blind_index
from jobs import queue
from ocr import repository as ocr_repo
from ocr.repository import ExtractionRecord
from ocr.verification import TaxLine, check_invoice_totals
from shared.audit import write_audit
from shared.config import get_settings
from shared.encryption import tenant_encryption_key, tenant_tax_id_blind_index
from shared.metrics import review_duration_seconds
from shared.rollout import FeatureFlag, is_rollout_enabled
from shared.tax_id import normalize_tax_id
from tenancy.constants import Role

INBOX_LIMIT = repository.INBOX_LIMIT

# `invoices.counterparty_tax_id`/`counterparty_name` viven cifrados por tenant desde S5.2 (pgcrypto,
# clave derivada con HKDF, `shared.encryption`). `counterparty_tax_id_blind_index` sustituye al
# filtro `ILIKE` retirado del panel (spec S5.2 C5): se recalcula aquí en cada escritura.

# Estados del fichero desde los que se puede revisar/confirmar (spec §2/§5): ya hay datos del OCR.
_CONFIRMABLE_STATES = frozenset({FileStatus.OCR_DONE.value, FileStatus.NEEDS_REVIEW.value})
_PROCESSING_STATES = frozenset({FileStatus.PENDING_OCR.value, FileStatus.PROCESSING.value})

AUDIT_ACTION_CONFIRM = "invoice.confirm"
_AUDIT_ENTITY = "invoice"


class InvoicingError(Exception):
    """Raíz de los errores de dominio de la persistencia de facturas."""


class CompanyForbidden(InvoicingError):
    """El actor no pertenece a la empresa del fichero (del propio tenant) (-> 403)."""


class FileNotVisible(InvoicingError):
    """El fichero no existe en el contexto del actor (inexistente u otro tenant) (-> 404)."""


class NotConfirmable(InvoicingError):
    """El fichero no está en un estado con datos de revisión/confirmación (-> 409)."""


class PendingOcr(NotConfirmable):
    """El fichero sigue en `pending_ocr`: el worker aún no ha terminado de leerlo (-> 409).

    Subclase de `NotConfirmable` para distinguir el caso transitorio (el cliente puede reintentar
    en segundo plano mientras procesa) de uno permanente (`ocr_failed`, ya confirmado): sin esta
    distinción, el frontend no puede saber si merece la pena esperar o debe mostrar un error ya.
    """


class CaptureUnreadable(NotConfirmable):
    """El fichero quedó en `capture_unreadable` (S6.14): la imagen en sí es el problema (-> 409).

    Subclase de `NotConfirmable` (mismo patrón que `PendingOcr`): un caso PERMANENTE y distinto de
    `ocr_failed` (el motor sí respondió, solo que sin nada aprovechable) y de un simple
    `needs_review` (aquí no hay formulario que abrir con campos vacíos, spec C7): el frontend debe
    explicar que hay que repetir la foto, no ofrecer revisar ni reintentar leer la MISMA imagen.
    """


class AlreadyConfirmed(InvoicingError):
    """Ya hay una factura para ese fichero (una factura por fichero) (-> 409)."""


class StructuredInvoicingError(InvoicingError):
    """Error de dominio que expone un contrato estructurado y actualizable para la pantalla."""

    def as_detail(self) -> dict[str, object]:
        raise NotImplementedError


class CounterpartyBlocked(StructuredInvoicingError):
    """El CIF de contraparte reverificado es inválido/inexistente: bloquea el guardado (-> 422)."""

    def __init__(self, verdict: CounterpartyVerdict) -> None:
        self.verdict = verdict

    def as_detail(self) -> dict[str, object]:
        reason = _counterparty_reason(self.verdict)
        assert reason is not None
        return {
            "code": reason,
            "counterparty_verdict": _verdict_dict(self.verdict),
            "blocking_reasons": [reason],
        }


class OwnTaxIdMissing(StructuredInvoicingError):
    """El CIF propio no aparece y el actor no es admin: bloquea el guardado (-> 422)."""

    def as_detail(self) -> dict[str, object]:
        return {"code": REASON_OWN_TAX_ID_MISSING, "blocking_reasons": [REASON_OWN_TAX_ID_MISSING]}


class ResponsibilityNotAccepted(InvoicingError):
    """No se aceptó la responsabilidad: bloquea el guardado (-> 422)."""


class InvoiceNotVisible(InvoicingError):
    """La factura no existe en el contexto del actor (inexistente u otro tenant) (-> 404, S3.3).

    A diferencia de `_load_file` (S2.5), aquí no hay un caso 403 aparte: el editor es siempre
    `tenant_admin` (spec S3.3, decisión de dominio 1), cuyo contexto ya abarca toda la asesoría
    (`app.company_id` sin fijar), así que no existe un "fichero de empresa hermana" que distinguir.
    """


class CounterpartyNameRequired(InvoicingError):
    """Cambiar el CIF de contraparte sin mandar también el nombre en el mismo `PATCH` (-> 422).

    Si solo cambiara el CIF, la reverificación (S2.8) comprobaría el nombre VIEJO contra el CIF
    NUEVO: la factura quedaría con `counterparty_cif_status = valid` pero un nombre que nadie ha
    verificado que coincida (hallazgo de auditoría S3.3). Se exige el nombre junto al CIF nuevo
    para que el veredicto sea real, no una verificación a medias.
    """


@dataclass(frozen=True)
class ConfirmTaxLine:
    """Un tramo de IVA tipado desde el body (del humano): confirmar (S2.5) o editar (S3.3)."""

    iva_pct: Decimal | None
    base: Decimal | None
    cuota: Decimal | None


@dataclass(frozen=True)
class ConfirmCommand:
    """Datos confirmados por el humano (ya tipados por el router; el servicio no conoce el HTTP)."""

    direction: str
    issue_date: date | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    net_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    irpf_amount: Decimal | None
    tax_lines: list[ConfirmTaxLine]
    responsibility_accepted: bool
    own_tax_id_exception_accepted: bool
    is_test: bool
    invoice_number: str | None = None


@dataclass(frozen=True)
class ReviewData:
    """Datos de revisión para la pantalla de confirmación (S2.4), solo lectura."""

    fields: dict[str, object]
    confidences: dict[str, object]
    counterparty_verdict: dict[str, object]
    own: dict[str, object]
    warnings: list[str]
    # Motivos por los que el servidor bloquearía el guardado (mismas guardas que `confirm`): la
    # pantalla deshabilita el botón si NO está vacía. Lista vacía = confirmable (S2.4 §2, C13).
    blocking_reasons: list[str]
    direction: str | None
    source: str = "ocr"
    draft_revision: int | None = None
    draft_updated_at: datetime | None = None
    page_count: int = 1


@dataclass(frozen=True)
class DraftCounterpartyVerdict:
    """Veredicto del CIF/nombre escrito ahora, sin efectos de persistencia (S6.10 C6)."""

    counterparty_verdict: dict[str, object]
    blocking_reasons: list[str]


@dataclass(frozen=True)
class HistoryItem:
    """Una entrada privada de documentos aceptados (S6.12), sin datos de contraparte.

    No reexporta `repository.HistoryEntry` tal cual: el router no debe depender de la forma interna
    de la capa de persistencia (misma separación que `ReviewData` frente a `ExtractionRecord`).
    """

    id: UUID
    status: str
    created_at: datetime
    direction: str | None


class InvalidInboxCursor(InvoicingError):
    """Cursor de bandeja ausente, corrupto o incompatible con su formato."""


@dataclass(frozen=True)
class InboxItem:
    id: UUID
    status: str
    processing_stage: str | None
    created_at: datetime
    direction: str | None
    page_count: int
    capture_session_id: UUID | None = None
    capture_sequence: int | None = None
    draft_updated_at: datetime | None = None


@dataclass(frozen=True)
class InboxSummary:
    processing: int
    ready: int
    attention: int


@dataclass(frozen=True)
class InboxData:
    items: list[InboxItem]
    summary: InboxSummary
    next_cursor: str | None


@dataclass(frozen=True)
class SupervisionItem:
    id: UUID
    user_email: str
    company_name: str
    status: str
    created_at: datetime
    direction: str | None
    page_count: int


@dataclass(frozen=True)
class SupervisionData:
    items: list[SupervisionItem]
    next_cursor: str | None


@dataclass(frozen=True)
class EditResult:
    """Estado de la factura tras aplicar (o no) una edición (S3.3): lo que responde el endpoint."""

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


@dataclass(frozen=True)
class PurgeResult:
    """Resultado de purgar las facturas de prueba (S3.5): cuántas se borraron."""

    purged: int


def _is_admin(role: str) -> bool:
    """True si el rol exime de las guardas de admin (CIF propio ausente, marcar `is_test`).

    Solo `tenant_admin`: el portero del endpoint es `require_roles(USER, TENANT_ADMIN)`, así que
    `platform_admin` no alcanza este endpoint (no se contempla aquí para no sugerir un camino que no
    existe).
    """
    return role == Role.TENANT_ADMIN.value


# Motivos de bloqueo del guardado (los consume la pantalla S2.4 y los reimpone `confirm`). Definidos
# UNA vez para que el botón y las guardas del servidor no puedan discrepar (única fuente de verdad).
REASON_CIF_INVALID = "counterparty_cif_invalid"
REASON_CIF_NOT_FOUND = "counterparty_cif_not_found"
REASON_OWN_TAX_ID_MISSING = "own_tax_id_missing"


def _counterparty_reason(verdict: CounterpartyVerdict) -> str | None:
    """Motivo de bloqueo por el CIF de contraparte, o `None` si no bloquea (C3/C4/C5)."""
    if verdict.status == CifStatus.INVALID:
        return REASON_CIF_INVALID
    if verdict.status == CifStatus.NOT_FOUND:
        return REASON_CIF_NOT_FOUND
    return None


async def _verify_counterparty_or_raise(
    tenant_id: UUID, tax_id: str | None, name: str | None
) -> CounterpartyVerdict:
    """Reverifica el CIF de contraparte (S2.8) y bloquea (`CounterpartyBlocked`) si no pasa.

    Compartido por `confirm` (S2.5, C3) y `edit_invoice` (S3.3): misma guarda de servidor, "no se
    confía en el cliente", en los dos únicos sitios donde un CIF de contraparte llega a persistirse.
    """
    verdict = await verify_counterparty(tenant_id, tax_id, name)
    if _counterparty_reason(verdict) is not None:
        raise CounterpartyBlocked(verdict)
    return verdict


def _own_tax_id_blocks(own_tax_id_present: bool, role: str) -> bool:
    """El CIF propio ausente bloquea, salvo que el actor sea admin (regla 2, C6)."""
    return not own_tax_id_present and not _is_admin(role)


def _own_tax_id_exception_blocks(
    own_tax_id_present: bool, role: str, exception_accepted: bool
) -> bool:
    """Un `user` solo puede confirmar el CIF propio ausente tras aceptarlo explícitamente."""
    return _own_tax_id_blocks(own_tax_id_present, role) and not exception_accepted


def _blocking_reasons(
    verdict: CounterpartyVerdict, own_tax_id_present: bool, role: str
) -> list[str]:
    """Motivos por los que el servidor bloquearía el guardado (misma lógica que `confirm`)."""
    reasons: list[str] = []
    cif_reason = _counterparty_reason(verdict)
    if cif_reason is not None:
        reasons.append(cif_reason)
    if _own_tax_id_blocks(own_tax_id_present, role):
        reasons.append(REASON_OWN_TAX_ID_MISSING)
    return reasons


async def _load_file(identity: AuthContext, file_id: UUID) -> intake_repo.UploadedFileContext:
    """Carga el fichero autorizando por contexto (RLS): 403 empresa ajena del tenant, 404 otro.

    Delega en `invoice_intake.service.authorize_file_edit`: el mismo aislamiento RLS que la descarga
    más el owner guard para impedir que un `tenant_admin` edite pendientes ajenas. Traduce las
    excepciones de `invoice_intake` a las propias de `invoicing`.
    """
    try:
        return await intake_service.authorize_file_edit(
            identity.session,
            tenant_id=identity.tenant_id,
            file_id=file_id,
            actor_user_id=identity.user_id,
            actor_role=identity.role,
        )
    except intake_service.FileForbidden as exc:
        raise CompanyForbidden from exc
    except intake_service.FileNotVisible as exc:
        raise FileNotVisible from exc


async def _load_visible_file(
    identity: AuthContext, file_id: UUID
) -> intake_repo.UploadedFileContext:
    """Carga un fichero para una pantalla explícitamente read-only de supervisión."""
    try:
        return await intake_service.authorize_file_access(
            identity.session,
            tenant_id=identity.tenant_id,
            file_id=file_id,
            actor_user_id=identity.user_id,
            actor_role=identity.role,
        )
    except intake_service.FileForbidden as exc:
        raise CompanyForbidden from exc
    except intake_service.FileNotVisible as exc:
        raise FileNotVisible from exc


def _raise_unless_confirmable(status: str) -> None:
    """Lanza la excepción que corresponde a un fichero NO confirmable (cascada S6.14).

    Tres estados posibles, cada uno con su excepción (y su `detail` HTTP) propios:
    `capture_unreadable` (S6.14, permanente: repetir la foto) -> `CaptureUnreadable`;
    `pending_ocr`/`processing` (transitorio: el worker sigue) -> `PendingOcr`; cualquier otro
    (`ocr_failed`, ya confirmado) -> `NotConfirmable`. El orden entre las dos primeras ramas es
    indiferente (sus conjuntos de estados son disjuntos); lo que SÍ es estructural es que
    `CaptureUnreadable`/`PendingOcr` sean subclases de `NotConfirmable` y se listen antes que ella
    en `_ERROR_STATUS` del router (first-match por isinstance).
    """
    if status == FileStatus.CAPTURE_UNREADABLE.value:
        raise CaptureUnreadable
    if status in _PROCESSING_STATES:
        raise PendingOcr
    raise NotConfirmable


def _balance_ok(
    lines: list[TaxLine], total: Decimal | None, irpf: Decimal | None = None
) -> bool | None:
    """`True`/`False` del cuadre aritmético, o `None` si faltan importes para comprobarlo.

    Descuenta el IRPF (retención) del total esperado si el humano lo aportó. El descuadre avisa pero
    no bloquea (regla 5): el resultado se guarda como aviso, nunca corta.
    """
    if total is None or not lines:
        return None
    return check_invoice_totals(lines, total, irpf_cuota=irpf or Decimal(0)).valid


def extraction_tax_lines(extraction: ExtractionRecord) -> list[TaxLine]:
    """Construye los `TaxLine` del cuadre desde la extracción (`[{base, rate, cuota}]`).

    Un tramo con algún importe ausente se descarta (no se puede cuadrar lo que no se leyó); si eso
    deja la lista vacía, el cuadre no es comprobable (`None`).

    Pública (2026-08-10, S6.6): reutilizada tal cual por `platform_admin.lab_service` para la
    columna 2 ("Lectura 1") de la fila de tramos de IVA del laboratorio -- mismo parseo que ya usa
    esta función para el cuadre y para el diff de confirmación, sin una segunda copia.
    """
    lines: list[TaxLine] = []
    for raw in extraction.tax_lines:
        base, rate, cuota = raw.get("base"), raw.get("rate"), raw.get("cuota")
        if base is None or rate is None or cuota is None:
            continue
        lines.append(
            TaxLine(base=Decimal(str(base)), iva_pct=Decimal(str(rate)), cuota=Decimal(str(cuota)))
        )
    return lines


def _command_tax_lines(command: ConfirmCommand) -> list[TaxLine]:
    """Construye los `TaxLine` del cuadre desde el body confirmado; descarta tramos incompletos."""
    lines: list[TaxLine] = []
    for line in command.tax_lines:
        if line.base is None or line.iva_pct is None or line.cuota is None:
            continue
        lines.append(TaxLine(base=line.base, iva_pct=line.iva_pct, cuota=line.cuota))
    return lines


def _draft_tax_lines(draft: draft_repository.DraftRecord) -> list[TaxLine]:
    """Convierte los tramos del snapshot al tipo común usado para comprobar el cuadre."""
    lines: list[TaxLine] = []
    for line in draft.tax_lines:
        base, rate, cuota = line.get("base"), line.get("iva_pct"), line.get("cuota")
        if base is None or rate is None or cuota is None:
            continue
        lines.append(
            TaxLine(
                base=Decimal(str(base)),
                iva_pct=Decimal(str(rate)),
                cuota=Decimal(str(cuota)),
            )
        )
    return lines


async def build_review_data(
    session: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    extraction: ExtractionRecord,
    role: str,
    counterparty_override: tuple[str | None, str | None] | None = None,
) -> ReviewData:
    """Calcula los datos de revisión (campos + confianzas + veredicto + avisos) a partir de una
    extracción OCR ya cargada (S2.4).

    Extraído de `review()` (S6.2, laboratorio admin-tech): la Lectura 2 del laboratorio necesita
    EXACTAMENTE este mismo cálculo pero sin la guarda de estado `_CONFIRMABLE_STATES` que sí aplica
    `review()` (spec docs/specs/S6.2-laboratorio-ocr-admin-tech.md C8/C9) — se factoriza aquí para
    que ambos llamantes compartan una única implementación, en vez de duplicar la lógica de negocio.
    Sin efectos secundarios ni comprobación de estado del fichero: solo lectura.
    """
    counterparty_tax_id, counterparty_name = counterparty_override or (
        extraction.counterparty_tax_id,
        extraction.counterparty_name,
    )
    verdict = await verify_counterparty(tenant_id, counterparty_tax_id, counterparty_name)
    own = await companies_repo.get_company(
        session,
        company_id,
        encryption_key=company_encryption_key(get_settings(), tenant_id),
    )

    warnings: list[str] = []
    if (
        _balance_ok(
            extraction_tax_lines(extraction), extraction.total_amount, extraction.irpf_amount
        )
        is False
    ):
        warnings.append("descuadre")
    if not extraction.own_tax_id_present:
        warnings.append("cif_propio_ausente")

    return ReviewData(
        fields={
            "issue_date": _iso(extraction.issue_date),
            "total_amount": _num(extraction.total_amount),
            "net_amount": _num(extraction.net_amount),
            "tax_amount": _num(extraction.tax_amount),
            "irpf_rate": _num(extraction.irpf_rate),
            "irpf_amount": _num(extraction.irpf_amount),
            "invoice_number": extraction.invoice_number,
            "counterparty_tax_id": extraction.counterparty_tax_id,
            "counterparty_name": extraction.counterparty_name,
            "tax_lines": extraction.tax_lines,
        },
        confidences=extraction.confidences,
        counterparty_verdict=_verdict_dict(verdict),
        own={
            "cif": own.cif if own is not None else None,
            "name": own.name if own is not None else None,
        },
        warnings=warnings,
        blocking_reasons=_blocking_reasons(verdict, extraction.own_tax_id_present, role),
        direction=None,
    )


async def review(identity: AuthContext, file_id: UUID, *, readonly: bool = False) -> ReviewData:
    """Datos de revisión de un fichero ya leído (S2.4): campos + confianzas + veredicto + avisos.

    Autoriza (403/404), exige estado confirmable con extracción (409), reverifica el CIF de
    contraparte en servidor (S2.8) y NO persiste nada.
    """
    file_ctx = (
        await _load_visible_file(identity, file_id)
        if readonly
        else await _load_file(identity, file_id)
    )
    if file_ctx.status not in _CONFIRMABLE_STATES:
        _raise_unless_confirmable(file_ctx.status)
    ocr_key = tenant_encryption_key(get_settings(), identity.tenant_id)
    extraction = await ocr_repo.get_extraction(identity.session, file_id, encryption_key=ocr_key)
    if extraction is None:
        raise NotConfirmable

    draft = await draft_repository.get(
        identity.session, uploaded_file_id=file_id, encryption_key=ocr_key
    )
    data = await build_review_data(
        identity.session,
        identity.tenant_id,
        file_ctx.company_id,
        extraction,
        identity.role,
        counterparty_override=(draft.counterparty_tax_id, draft.counterparty_name)
        if draft is not None
        else None,
    )
    page_count = len(await intake_repo.get_document_pages(identity.session, file_id))
    if draft is None:
        return replace(data, direction=file_ctx.direction, page_count=page_count)

    draft_tax_lines = [
        {
            "base": line.get("base"),
            "rate": line.get("iva_pct"),
            "cuota": line.get("cuota"),
        }
        for line in draft.tax_lines
    ]
    fields = {
        **data.fields,
        "issue_date": _iso(draft.issue_date),
        "total_amount": _num(draft.total_amount),
        "net_amount": _num(draft.net_amount),
        "tax_amount": _num(draft.tax_amount),
        "irpf_amount": _num(draft.irpf_amount),
        "invoice_number": draft.invoice_number,
        "counterparty_tax_id": draft.counterparty_tax_id,
        "counterparty_name": draft.counterparty_name,
        "tax_lines": draft_tax_lines,
    }
    draft_warnings = []
    if _balance_ok(_draft_tax_lines(draft), draft.total_amount, draft.irpf_amount) is False:
        draft_warnings.append("descuadre")
    if not extraction.own_tax_id_present:
        draft_warnings.append("cif_propio_ausente")
    return replace(
        data,
        fields=fields,
        warnings=draft_warnings,
        direction=draft.direction or file_ctx.direction,
        source="draft",
        draft_revision=draft.revision,
        draft_updated_at=draft.updated_at,
        page_count=page_count,
    )


async def draft_counterparty_verdict(
    identity: AuthContext,
    file_id: UUID,
    counterparty_tax_id: str | None,
    counterparty_name: str | None,
) -> DraftCounterpartyVerdict:
    """Devuelve la validación del borrador actual sin reutilizar el veredicto del OCR (S6.10 C6)."""
    file_ctx = await _load_file(identity, file_id)
    if file_ctx.status not in _CONFIRMABLE_STATES:
        _raise_unless_confirmable(file_ctx.status)
    ocr_key = tenant_encryption_key(get_settings(), identity.tenant_id)
    if await ocr_repo.get_extraction(identity.session, file_id, encryption_key=ocr_key) is None:
        raise NotConfirmable
    verdict = await verify_counterparty(identity.tenant_id, counterparty_tax_id, counterparty_name)
    return DraftCounterpartyVerdict(
        counterparty_verdict=_verdict_dict(verdict),
        blocking_reasons=[reason] if (reason := _counterparty_reason(verdict)) is not None else [],
    )


async def confirm(identity: AuthContext, file_id: UUID, command: ConfirmCommand) -> UUID:
    """Confirma un fichero: persiste la factura, tramos, correcciones, snapshot y transición (201).

    Orden y guardas de servidor: autorización (403/404) -> estado confirmable + no reconfirmable
    (409) -> guardas locales baratas y deterministas (CIF propio ausente salvo admin;
    responsabilidad aceptada; 422) -> reverificación del CIF de contraparte con S2.8 (422 si
    bloquea; puede tocar red L3, por eso va DESPUÉS de las locales) -> descuadre (aviso) ->
    persistencia atómica (factura + tramos + correcciones + snapshot en audit + transición +
    supplier master en la MISMA transacción, spec §4).
    """
    file_ctx = await _load_file(identity, file_id)
    if file_ctx.status not in _CONFIRMABLE_STATES:
        _raise_unless_confirmable(file_ctx.status)
    if await repository.invoice_exists_for_file(identity.session, file_id):
        raise AlreadyConfirmed
    ocr_key = tenant_encryption_key(get_settings(), identity.tenant_id)
    extraction = await ocr_repo.get_extraction(identity.session, file_id, encryption_key=ocr_key)
    if extraction is None:
        raise NotConfirmable
    draft = await draft_repository.get(
        identity.session, uploaded_file_id=file_id, encryption_key=ocr_key
    )
    if draft is not None:
        # El snapshot persistido es la versión que el servidor debe confirmar. El body conserva solo
        # decisiones que no forman parte del borrador, como responsabilidad, excepción e is_test.
        command = replace(
            command,
            direction=draft.direction or file_ctx.direction or command.direction,
            issue_date=draft.issue_date,
            counterparty_tax_id=draft.counterparty_tax_id,
            counterparty_name=draft.counterparty_name,
            invoice_number=draft.invoice_number,
            net_amount=draft.net_amount,
            tax_amount=draft.tax_amount,
            total_amount=draft.total_amount,
            irpf_amount=draft.irpf_amount,
            tax_lines=[
                ConfirmTaxLine(
                    iva_pct=(
                        Decimal(str(line["iva_pct"])) if line.get("iva_pct") is not None else None
                    ),
                    base=Decimal(str(line["base"])) if line.get("base") is not None else None,
                    cuota=Decimal(str(line["cuota"])) if line.get("cuota") is not None else None,
                )
                for line in draft.tax_lines
            ],
        )
    # La captura manda sobre el body cuando ya existe. Para documentos anteriores a S6.13 la
    # dirección sigue siendo nula y el valor explícito del humano conserva la compatibilidad.
    command = replace(command, direction=file_ctx.direction or command.direction)

    # Guardas locales baratas y deterministas ANTES de la reverificación (que puede tocar red L3):
    # un usuario que no acepta la responsabilidad o sin el CIF propio no dispara lookups externos.
    # CIF propio ausente bloquea, salvo admin (regla 2, C4). Mismo predicado que `blocking_reasons`.
    if _own_tax_id_exception_blocks(
        extraction.own_tax_id_present, identity.role, command.own_tax_id_exception_accepted
    ):
        raise OwnTaxIdMissing
    # Sin aceptar la responsabilidad no hay factura (regla 8, C5).
    if not command.responsibility_accepted:
        raise ResponsibilityNotAccepted

    # Reverifica el CIF de contraparte del BODY con S2.8 (no se confía en el cliente, C3).
    verdict = await _verify_counterparty_or_raise(
        identity.tenant_id, command.counterparty_tax_id, command.counterparty_name
    )

    # Descuadre = aviso, no bloqueo (regla 5, C6): se guarda con el resultado registrado.
    balance_ok = _balance_ok(_command_tax_lines(command), command.total_amount, command.irpf_amount)

    # `is_test` solo lo puede marcar un admin; si lo envía un `user`, se ignora (queda false, C11).
    is_test = command.is_test and _is_admin(identity.role)
    own_tax_id_missing = not extraction.own_tax_id_present
    own_tax_id_exception_confirmed = (
        own_tax_id_missing
        and identity.role == Role.USER.value
        and command.own_tax_id_exception_accepted
    )

    corrections = _diff(extraction, command)
    snapshot = _snapshot(
        command,
        verdict,
        balance_ok,
        own_tax_id_missing=own_tax_id_missing,
        own_tax_id_exception_confirmed=own_tax_id_exception_confirmed,
    )
    settings = get_settings()
    encryption_key = tenant_encryption_key(settings, identity.tenant_id)
    tax_id_idx = tenant_tax_id_blind_index(
        settings, identity.tenant_id, command.counterparty_tax_id
    )

    # Persistencia atómica en la transacción de la petición (spec §4). El UNIQUE por fichero cierra
    # la carrera de dos confirmaciones concurrentes que ambas pasaron el pre-check: la violación se
    # traduce a 409 (una factura por fichero, C9), no a un 500.
    try:
        invoice_id = await repository.insert_invoice(
            identity.session,
            company_id=file_ctx.company_id,
            uploaded_file_id=file_id,
            direction=command.direction,
            issue_date=command.issue_date,
            counterparty_tax_id=command.counterparty_tax_id,
            counterparty_tax_id_blind_index=tax_id_idx,
            counterparty_name=command.counterparty_name,
            counterparty_cif_status=verdict.status,
            invoice_number=command.invoice_number,
            net_amount=command.net_amount,
            tax_amount=command.tax_amount,
            total_amount=command.total_amount,
            irpf_amount=command.irpf_amount,
            is_test=is_test,
            balance_ok=balance_ok,
            own_tax_id_missing=own_tax_id_missing,
            own_tax_id_exception_confirmed=own_tax_id_exception_confirmed,
            snapshot=snapshot,
            confirmed_by=identity.user_id,
            encryption_key=encryption_key,
        )
    except IntegrityError as exc:
        if repository.is_duplicate_invoice(exc):
            raise AlreadyConfirmed from exc
        raise
    await repository.insert_tax_lines(
        identity.session,
        invoice_id=invoice_id,
        company_id=file_ctx.company_id,
        lines=[(line.iva_pct, line.base, line.cuota) for line in command.tax_lines],
    )
    await repository.insert_corrections(
        identity.session,
        invoice_id=invoice_id,
        uploaded_file_id=file_id,
        company_id=file_ctx.company_id,
        corrected_by=identity.user_id,
        corrections=corrections,
    )
    # El snapshot (datos confirmados + responsabilidad + descuadre) queda ligado a la entrada del
    # audit_log por `payload_hash` (S2.5 §4/C8), sin duplicar el dato crudo en el log.
    await write_audit(
        identity.session,
        actor_id=identity.user_id,
        action=AUDIT_ACTION_CONFIRM,
        entity=_AUDIT_ENTITY,
        entity_id=invoice_id,
        payload=snapshot,
    )
    await intake_repo.transition_status(identity.session, file_id, FileStatus.CONFIRMED)
    await draft_repository.delete(identity.session, uploaded_file_id=file_id)

    # Alimenta el supplier master del tenant (S2.8) EN LA MISMA transacción (sesión inyectada): la
    # próxima verificación de ese CIF acertará por L2. El CIF ya pasó L1 (verify no lo marcó
    # `invalid`), así que `record_confirmation` no rechaza.
    await record_confirmation(
        identity.tenant_id,
        command.counterparty_tax_id or "",
        command.counterparty_name or "",
        settings=settings,
        session=identity.session,
    )

    # Aprende solo después de que la factura, la auditoría y el estado confirmado se hayan escrito
    # en esta misma transacción. El perfil guarda patrones agregados, nunca el CIF en claro ni la
    # factura anterior completa.
    if command.counterparty_tax_id and is_rollout_enabled(
        settings, FeatureFlag.SUPPLIER_LEARNING, identity.tenant_id
    ):
        profile_features = build_profile_features(
            invoice_number=command.invoice_number,
            tax_rates=[line.iva_pct for line in command.tax_lines if line.iva_pct is not None],
            tax_line_count=len(command.tax_lines),
            corrections=corrections,
        )
        await supplier_profile_repository.upsert(
            identity.session,
            tenant_id=identity.tenant_id,
            company_id=file_ctx.company_id,
            counterparty_cif_blind_index=supplier_profile_blind_index(
                settings,
                identity.tenant_id,
                file_ctx.company_id,
                command.counterparty_tax_id,
            ),
            features=profile_features,
        )

    _enqueue_benchmark_after_commit(
        identity.session, identity.tenant_id, file_ctx.company_id, file_id
    )
    if file_ctx.ocr_finished_at is not None:
        review_duration_seconds.observe(
            max((datetime.now(UTC) - file_ctx.ocr_finished_at).total_seconds(), 0.0)
        )
    return invoice_id


def _enqueue_benchmark_after_commit(
    session: AsyncSession, tenant_id: UUID, company_id: UUID, file_id: UUID
) -> None:
    """Encola el benchmark solo tras confirmar la factura (S6.7 C1).

    El worker debe poder leer la verdad confirmada. Hacerlo dentro de `confirm` dejaba una carrera
    real: podía consumir el trabajo antes del commit y abandonar al no encontrar la factura.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    def _enqueue(_sync_session: Session) -> None:
        asyncio.get_running_loop().create_task(
            queue.enqueue_ocr_benchmark(str(tenant_id), str(company_id), str(file_id))
        )

    event.listen(session.sync_session, "after_commit", _enqueue, once=True)


async def history(identity: AuthContext) -> list[HistoryItem]:
    """Historial de los 20 últimos documentos aceptados del contexto (S6.12). Solo lectura.

    Autorización de fichero por-fila no aplica aquí (a diferencia de `review`/`confirm`, que cargan
    UN fichero): la RLS de dos niveles ya acota el resultado al tenant/empresa de la sesión (spec
    §4). Un `user` recibe además el filtro `confirmed_by` (2026-08-02, cumplimiento): dentro de su
    propia empresa, solo ve lo que confirmó él mismo, nunca lo de un compañero. Un `tenant_admin`
    conserva la vista completa de su asesoría (spec original, sin cambios).
    """
    entries = await repository.list_history(
        identity.session,
        uploaded_by=identity.user_id if identity.role == Role.USER else None,
    )
    return [
        HistoryItem(
            id=entry.id,
            status=entry.status,
            created_at=entry.created_at,
            direction=entry.direction,
        )
        for entry in entries
    ]


def _encode_inbox_cursor(created_at: datetime, item_id: UUID) -> str:
    """Codifica solo la posición de orden, nunca datos de la factura."""
    payload = json.dumps([created_at.isoformat(), str(item_id)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_inbox_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decodifica el cursor compuesto o rechaza la petición sin consultar datos."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at_raw, item_id_raw = json.loads(base64.urlsafe_b64decode(padded).decode())
        created_at = datetime.fromisoformat(created_at_raw)
        if created_at.tzinfo is None:
            raise ValueError
        return created_at, UUID(item_id_raw)
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
        KeyError,
    ) as exc:
        raise InvalidInboxCursor from exc


async def inbox(identity: AuthContext, *, cursor: str | None, limit: int) -> InboxData:
    """Bandeja personal SELF ONLY, también para `tenant_admin` (R-020)."""
    cursor_created_at: datetime | None = None
    cursor_id: UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_inbox_cursor(cursor)
    page = await repository.list_inbox(
        identity.session,
        uploaded_by=identity.user_id,
        limit=limit,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    items = [
        InboxItem(
            id=entry.id,
            status=entry.status,
            processing_stage=entry.processing_stage,
            created_at=entry.created_at,
            direction=entry.direction,
            page_count=entry.page_count,
            capture_session_id=entry.capture_session_id,
            capture_sequence=entry.capture_sequence,
        )
        for entry in page.items
    ]
    next_cursor = (
        _encode_inbox_cursor(items[-1].created_at, items[-1].id) if page.has_more else None
    )
    return InboxData(
        items=items,
        summary=InboxSummary(
            processing=page.summary.processing,
            ready=page.summary.ready,
            attention=page.summary.attention,
        ),
        next_cursor=next_cursor,
    )


async def supervision(identity: AuthContext, *, cursor: str | None, limit: int) -> SupervisionData:
    """Pendientes de otros usuarios del tenant para la vista read-only del administrador (R-026)."""
    cursor_created_at: datetime | None = None
    cursor_id: UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_inbox_cursor(cursor)
    page = await repository.list_supervision(
        identity.session,
        actor_user_id=identity.user_id,
        limit=limit,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        encryption_key=tenant_encryption_key(get_settings(), identity.tenant_id),
    )
    items = [
        SupervisionItem(
            id=entry.id,
            user_email=entry.user_email,
            company_name=entry.company_name,
            status=entry.status,
            created_at=entry.created_at,
            direction=entry.direction,
            page_count=entry.page_count,
        )
        for entry in page.items
    ]
    next_cursor = (
        _encode_inbox_cursor(items[-1].created_at, items[-1].id) if page.has_more else None
    )
    return SupervisionData(items=items, next_cursor=next_cursor)


AUDIT_ACTION_EDIT = "invoice.edit"


def _lines_from_raw(
    raw: list[tuple[Decimal | None, Decimal | None, Decimal | None]],
) -> list[TaxLine]:
    """`TaxLine` completos desde las tuplas crudas de `repository.InvoiceRecord`; descarta
    incompletos (igual criterio que `extraction_tax_lines`/`_command_tax_lines`)."""
    lines: list[TaxLine] = []
    for iva_pct, base, cuota in raw:
        if iva_pct is None or base is None or cuota is None:
            continue
        lines.append(TaxLine(iva_pct=iva_pct, base=base, cuota=cuota))
    return lines


def _lines_from_edit(raw: list[ConfirmTaxLine]) -> list[TaxLine]:
    """`TaxLine` completos desde los tramos del `PATCH`; descarta incompletos."""
    lines: list[TaxLine] = []
    for line in raw:
        if line.iva_pct is None or line.base is None or line.cuota is None:
            continue
        lines.append(TaxLine(iva_pct=line.iva_pct, base=line.base, cuota=line.cuota))
    return lines


@dataclass(frozen=True)
class _MergedFields:
    """El `PATCH` parcial fusionado con el valor actual: un campo ausente conserva su valor."""

    issue_date: date | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    net_amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    irpf_amount: Decimal | None
    tax_lines: list[TaxLine]


def _merge_patch(current: repository.InvoiceRecord, patch: Mapping[str, Any]) -> _MergedFields:
    """Fusiona `patch` con `current`: cada campo ausente en `patch` conserva el valor actual."""
    tax_lines = (
        _lines_from_edit(patch["tax_lines"])
        if "tax_lines" in patch
        else _lines_from_raw(current.tax_lines)
    )
    return _MergedFields(
        issue_date=patch.get("issue_date", current.issue_date),
        counterparty_tax_id=patch.get("counterparty_tax_id", current.counterparty_tax_id),
        counterparty_name=patch.get("counterparty_name", current.counterparty_name),
        net_amount=patch.get("net_amount", current.net_amount),
        tax_amount=patch.get("tax_amount", current.tax_amount),
        total_amount=patch.get("total_amount", current.total_amount),
        irpf_amount=patch.get("irpf_amount", current.irpf_amount),
        tax_lines=tax_lines,
    )


async def _maybe_reverify_cif(
    identity: AuthContext,
    current: repository.InvoiceRecord,
    merged: _MergedFields,
    patch: Mapping[str, Any],
) -> str:
    """Reverifica el CIF SOLO si cambia de verdad (spec §2 decisión 3); si no, conserva el estado.

    Si el CIF cambia pero el `PATCH` no trae también `counterparty_name`, exige ambos juntos
    (`CounterpartyNameRequired`): reverificar el CIF nuevo contra el nombre VIEJO dejaría la
    factura en `valid` con un nombre que nadie ha comprobado que coincida (hallazgo de auditoría).
    """
    if "counterparty_tax_id" not in patch:
        return current.counterparty_cif_status
    if normalize_tax_id(merged.counterparty_tax_id) == normalize_tax_id(
        current.counterparty_tax_id
    ):
        return current.counterparty_cif_status
    if "counterparty_name" not in patch:
        raise CounterpartyNameRequired
    verdict = await _verify_counterparty_or_raise(
        identity.tenant_id, merged.counterparty_tax_id, merged.counterparty_name
    )
    return verdict.status


def _edit_diff(current: repository.InvoiceRecord, merged: _MergedFields) -> list[Correction]:
    """Correcciones = diff del `PATCH` fusionado contra el valor anterior de la factura (S3.3)."""
    baseline = BaselineFields(
        issue_date=current.issue_date,
        total_amount=current.total_amount,
        net_amount=current.net_amount,
        tax_amount=current.tax_amount,
        counterparty_tax_id=current.counterparty_tax_id,
        counterparty_name=current.counterparty_name,
        tax_lines=_tax_line_fields(_lines_from_raw(current.tax_lines)),
    )
    confirmed = ConfirmedFields(
        issue_date=merged.issue_date,
        total_amount=merged.total_amount,
        net_amount=merged.net_amount,
        tax_amount=merged.tax_amount,
        counterparty_tax_id=merged.counterparty_tax_id,
        counterparty_name=merged.counterparty_name,
        tax_lines=_tax_line_fields(merged.tax_lines),
    )
    return diff_corrections(baseline, confirmed)


def _edit_result(
    invoice_id: UUID, merged: _MergedFields, *, cif_status: str, balance_ok: bool | None
) -> EditResult:
    return EditResult(
        id=invoice_id,
        issue_date=merged.issue_date,
        counterparty_tax_id=merged.counterparty_tax_id,
        counterparty_name=merged.counterparty_name,
        counterparty_cif_status=cif_status,
        net_amount=merged.net_amount,
        tax_amount=merged.tax_amount,
        total_amount=merged.total_amount,
        irpf_amount=merged.irpf_amount,
        balance_ok=balance_ok,
    )


async def edit_invoice(
    identity: AuthContext, invoice_id: UUID, patch: Mapping[str, Any]
) -> EditResult:
    """Edita los campos presentes en `patch` de una factura ya confirmada (S3.3, `tenant_admin`).

    `patch` solo trae las claves que el cliente envió (patch parcial real, spec §2). Sin cambios
    reales (el diff sale vacío) no escribe nada: ni `invoices`, ni `invoice_tax_lines`, ni
    `invoice_edits`, ni `audit_log` (spec §2, "sin cambios reales = sin efecto observable").
    """
    settings = get_settings()
    encryption_key = tenant_encryption_key(settings, identity.tenant_id)
    current = await repository.get_invoice(
        identity.session, invoice_id, encryption_key=encryption_key
    )
    if current is None:
        raise InvoiceNotVisible

    merged = _merge_patch(current, patch)
    cif_status = await _maybe_reverify_cif(identity, current, merged, patch)
    # Regla 5: el descuadre avisa, nunca bloquea; se calcula una sola vez y sirve tanto si hay
    # cambios reales como si no (evita recomputarlo dos veces con el riesgo de que diverjan).
    balance_ok = _balance_ok(merged.tax_lines, merged.total_amount, merged.irpf_amount)
    edits = _edit_diff(current, merged)

    if not edits:
        return _edit_result(invoice_id, merged, cif_status=cif_status, balance_ok=balance_ok)

    await repository.update_invoice(
        identity.session,
        invoice_id,
        issue_date=merged.issue_date,
        counterparty_tax_id=merged.counterparty_tax_id,
        counterparty_tax_id_blind_index=tenant_tax_id_blind_index(
            settings, identity.tenant_id, merged.counterparty_tax_id
        ),
        counterparty_name=merged.counterparty_name,
        counterparty_cif_status=cif_status,
        net_amount=merged.net_amount,
        tax_amount=merged.tax_amount,
        total_amount=merged.total_amount,
        irpf_amount=merged.irpf_amount,
        balance_ok=balance_ok,
        encryption_key=encryption_key,
    )
    if "tax_lines" in patch:
        await repository.delete_tax_lines(identity.session, invoice_id)
        await repository.insert_tax_lines(
            identity.session,
            invoice_id=invoice_id,
            company_id=current.company_id,
            lines=[(line.iva_pct, line.base, line.cuota) for line in merged.tax_lines],
        )
    await repository.insert_edits(
        identity.session,
        invoice_id=invoice_id,
        company_id=current.company_id,
        edited_by=identity.user_id,
        edits=edits,
        encryption_key=encryption_key,
    )
    await write_audit(
        identity.session,
        actor_id=identity.user_id,
        action=AUDIT_ACTION_EDIT,
        entity=_AUDIT_ENTITY,
        entity_id=invoice_id,
        payload={edit.field: {"old": edit.ai_value, "new": edit.human_value} for edit in edits},
    )
    return _edit_result(invoice_id, merged, cif_status=cif_status, balance_ok=balance_ok)


async def invoice_history(
    identity: AuthContext, invoice_id: UUID
) -> list[repository.InvoiceEditEntry]:
    """Historial de ediciones de una factura del contexto, más reciente primero (2026-08-01).

    Factura fuera del contexto (otro tenant/empresa, o inexistente) -> `InvoiceNotVisible` (404),
    igual que `edit_invoice`.
    """
    settings = get_settings()
    encryption_key = tenant_encryption_key(settings, identity.tenant_id)
    current = await repository.get_invoice(
        identity.session, invoice_id, encryption_key=encryption_key
    )
    if current is None:
        raise InvoiceNotVisible
    return await repository.list_edits(identity.session, invoice_id, encryption_key=encryption_key)


AUDIT_ACTION_PURGE_TEST = "invoice.purge_test"


async def purge_test_invoices(identity: AuthContext) -> PurgeResult:
    """Borra TODAS las facturas de prueba visibles en el contexto, de una vez (S3.5).

    La condición `is_test = true` es fija en el repositorio, nunca un parámetro de esta función ni
    del endpoint (spec S3.5 regla 2): estructuralmente no puede alcanzar una factura real. Cada
    factura purgada deja su propia entrada `invoice.purge_test` en `audit_log` (regla 6, no una fila
    agregada); su fichero subido se borra a través de `invoice_intake` (dueño de `uploaded_files` y
    de MinIO), misma llamada cruzada de contexto que `_load_file` usa para autorizar (S2.5/S2.7). El
    borrado del OBJETO en MinIO se agenda para después del commit (`schedule_storage_cleanup`): la
    fila de Postgres se borra ya, dentro de esta transacción; la red a MinIO no la alarga.
    """
    purged = await repository.purge_test_invoices(identity.session)
    locations = []
    for item in purged:
        await write_audit(
            identity.session,
            actor_id=identity.user_id,
            action=AUDIT_ACTION_PURGE_TEST,
            entity=_AUDIT_ENTITY,
            entity_id=item.id,
            payload={"uploaded_file_id": str(item.uploaded_file_id)},
        )
        file_locations = await intake_service.delete_uploaded_file_row(
            identity.session, item.uploaded_file_id
        )
        locations.extend(file_locations)
    intake_service.schedule_storage_cleanup(identity.session, locations)
    return PurgeResult(purged=len(purged))


def _diff(extraction: ExtractionRecord, command: ConfirmCommand) -> list[Correction]:
    """Correcciones = diff del body confirmado contra el baseline del OCR (S2.3)."""
    baseline = BaselineFields(
        issue_date=extraction.issue_date,
        total_amount=extraction.total_amount,
        net_amount=extraction.net_amount,
        tax_amount=extraction.tax_amount,
        counterparty_tax_id=extraction.counterparty_tax_id,
        counterparty_name=extraction.counterparty_name,
        invoice_number=extraction.invoice_number,
        tax_lines=_tax_line_fields(extraction_tax_lines(extraction)),
    )
    confirmed = ConfirmedFields(
        issue_date=command.issue_date,
        total_amount=command.total_amount,
        net_amount=command.net_amount,
        tax_amount=command.tax_amount,
        counterparty_tax_id=command.counterparty_tax_id,
        counterparty_name=command.counterparty_name,
        invoice_number=command.invoice_number,
        tax_lines=_tax_line_fields(_command_tax_lines(command)),
    )
    return diff_corrections(baseline, confirmed)


def _tax_line_fields(lines: list[TaxLine]) -> tuple[TaxLineFields, ...]:
    """Adapta los tramos internos (`TaxLine`) al tipo del diff (`TaxLineFields`)."""
    return tuple(
        TaxLineFields(iva_pct=line.iva_pct, base=line.base, cuota=line.cuota) for line in lines
    )


def _snapshot(
    command: ConfirmCommand,
    verdict: CounterpartyVerdict,
    balance_ok: bool | None,
    *,
    own_tax_id_missing: bool,
    own_tax_id_exception_confirmed: bool,
) -> dict[str, object]:
    """Snapshot append-only de lo confirmado (datos + aceptación) para la traza (audit_log)."""
    return {
        "direction": command.direction,
        "issue_date": _iso(command.issue_date),
        "counterparty_tax_id": command.counterparty_tax_id,
        "counterparty_name": command.counterparty_name,
        "counterparty_cif_status": verdict.status,
        "invoice_number": command.invoice_number,
        "net_amount": _num(command.net_amount),
        "tax_amount": _num(command.tax_amount),
        "total_amount": _num(command.total_amount),
        "irpf_amount": _num(command.irpf_amount),
        "tax_lines": [
            {"iva_pct": _num(line.iva_pct), "base": _num(line.base), "cuota": _num(line.cuota)}
            for line in command.tax_lines
        ],
        "responsibility_accepted": command.responsibility_accepted,
        "own_tax_id_missing": own_tax_id_missing,
        "own_tax_id_exception_accepted": own_tax_id_exception_confirmed,
        "balance_ok": balance_ok,
    }


def _verdict_dict(verdict: CounterpartyVerdict) -> dict[str, object]:
    """Proyección del veredicto del CIF para la revisión (status/name_match/official_name)."""
    return {
        "status": verdict.status,
        "name_match": verdict.name_match,
        "official_name": verdict.official_name,
    }


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _num(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
