"""Lógica de dominio de la persistencia de facturas (S2.5): orquesta `review` y `confirm`.

El router HTTP es fino: traduce la petición a estas operaciones y sus excepciones de dominio a
códigos HTTP. Aquí viven las guardas de servidor (spec §4, "el servidor no confía en el cliente"):
reverifica el CIF de contraparte con S2.8, reimpone el CIF propio presente (salvo admin) y la
aceptación de responsabilidad, y se persiste TODO en la transacción de la petición (atomicidad):
factura + tramos + correcciones (diff vs OCR) + snapshot en `audit_log` + transición del fichero. El
descuadre aritmético AVISA pero no bloquea (regla 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from companies import repository as companies_repo
from counterparty.constants import CifStatus
from counterparty.service import CounterpartyVerdict, record_confirmation, verify_counterparty
from identity.dependencies import AuthContext
from invoice_intake import repository as intake_repo
from invoice_intake.constants import FileStatus
from invoicing import repository
from invoicing.corrections import (
    BaselineFields,
    ConfirmedFields,
    Correction,
    TaxLineFields,
    diff_corrections,
)
from ocr import repository as ocr_repo
from ocr.repository import ExtractionRecord
from ocr.verification import TaxLine, check_invoice_totals
from shared.audit import write_audit
from shared.db import tenant_session
from tenancy.constants import Role

# Estados del fichero desde los que se puede revisar/confirmar (spec §2/§5): ya hay datos del OCR.
_CONFIRMABLE_STATES = frozenset({FileStatus.OCR_DONE.value, FileStatus.NEEDS_REVIEW.value})

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


class AlreadyConfirmed(InvoicingError):
    """Ya hay una factura para ese fichero (una factura por fichero) (-> 409)."""


class CounterpartyBlocked(InvoicingError):
    """El CIF de contraparte reverificado es inválido/inexistente: bloquea el guardado (-> 422)."""


class OwnTaxIdMissing(InvoicingError):
    """El CIF propio no aparece y el actor no es admin: bloquea el guardado (-> 422)."""


class ResponsibilityNotAccepted(InvoicingError):
    """No se aceptó la responsabilidad: bloquea el guardado (-> 422)."""


@dataclass(frozen=True)
class ConfirmTaxLine:
    """Un tramo de IVA confirmado por el humano (valores tipados desde el body)."""

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
    is_test: bool


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


def _own_tax_id_blocks(own_tax_id_present: bool, role: str) -> bool:
    """El CIF propio ausente bloquea, salvo que el actor sea admin (regla 2, C6)."""
    return not own_tax_id_present and not _is_admin(role)


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

    Reutiliza el patrón de `invoice_intake.authorize_upload`: si el fichero es visible en el
    contexto de la petición (empresa del `user` o asesoría del `tenant_admin`), el actor está
    autorizado. Si no, se abre una sesión de asesoría (ve todo el tenant) para distinguir un fichero
    de una empresa hermana del propio tenant (403) de uno de otro tenant/inexistente (404).
    """
    ctx = await intake_repo.get_file_context(identity.session, file_id)
    if ctx is not None:
        return ctx
    async with tenant_session(identity.tenant_id) as sess:
        in_tenant = await intake_repo.get_file_context(sess, file_id)
    if in_tenant is not None:
        raise CompanyForbidden
    raise FileNotVisible


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


def _extraction_tax_lines(extraction: ExtractionRecord) -> list[TaxLine]:
    """Construye los `TaxLine` del cuadre desde la extracción (`[{base, rate, cuota}]`).

    Un tramo con algún importe ausente se descarta (no se puede cuadrar lo que no se leyó); si eso
    deja la lista vacía, el cuadre no es comprobable (`None`).
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


async def review(identity: AuthContext, file_id: UUID) -> ReviewData:
    """Datos de revisión de un fichero ya leído (S2.4): campos + confianzas + veredicto + avisos.

    Autoriza (403/404), exige estado confirmable con extracción (409), reverifica el CIF de
    contraparte en servidor (S2.8) y NO persiste nada.
    """
    file_ctx = await _load_file(identity, file_id)
    if file_ctx.status not in _CONFIRMABLE_STATES:
        raise NotConfirmable
    extraction = await ocr_repo.get_extraction(identity.session, file_id)
    if extraction is None:
        raise NotConfirmable

    verdict = await verify_counterparty(
        identity.tenant_id, extraction.counterparty_tax_id, extraction.counterparty_name
    )
    own = await companies_repo.get_company(identity.session, file_ctx.company_id)

    warnings: list[str] = []
    if _balance_ok(_extraction_tax_lines(extraction), extraction.total_amount) is False:
        warnings.append("descuadre")
    if not extraction.own_tax_id_present:
        warnings.append("cif_propio_ausente")

    return ReviewData(
        fields={
            "issue_date": _iso(extraction.issue_date),
            "total_amount": _num(extraction.total_amount),
            "net_amount": _num(extraction.net_amount),
            "tax_amount": _num(extraction.tax_amount),
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
        blocking_reasons=_blocking_reasons(
            verdict, extraction.own_tax_id_present, identity.role
        ),
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
        raise NotConfirmable
    if await repository.invoice_exists_for_file(identity.session, file_id):
        raise AlreadyConfirmed
    extraction = await ocr_repo.get_extraction(identity.session, file_id)
    if extraction is None:
        raise NotConfirmable

    # Guardas locales baratas y deterministas ANTES de la reverificación (que puede tocar red L3):
    # un usuario que no acepta la responsabilidad o sin el CIF propio no dispara lookups externos.
    # CIF propio ausente bloquea, salvo admin (regla 2, C4). Mismo predicado que `blocking_reasons`.
    if _own_tax_id_blocks(extraction.own_tax_id_present, identity.role):
        raise OwnTaxIdMissing
    # Sin aceptar la responsabilidad no hay factura (regla 8, C5).
    if not command.responsibility_accepted:
        raise ResponsibilityNotAccepted

    # Reverifica el CIF de contraparte del BODY con S2.8 (no se confía en el cliente, C3).
    verdict = await verify_counterparty(
        identity.tenant_id, command.counterparty_tax_id, command.counterparty_name
    )
    if _counterparty_reason(verdict) is not None:
        raise CounterpartyBlocked

    # Descuadre = aviso, no bloqueo (regla 5, C6): se guarda con el resultado registrado.
    balance_ok = _balance_ok(_command_tax_lines(command), command.total_amount, command.irpf_amount)

    # `is_test` solo lo puede marcar un admin; si lo envía un `user`, se ignora (queda false, C11).
    is_test = command.is_test and _is_admin(identity.role)

    corrections = _diff(extraction, command)
    snapshot = _snapshot(command, verdict, balance_ok)

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
            counterparty_name=command.counterparty_name,
            counterparty_cif_status=verdict.status,
            net_amount=command.net_amount,
            tax_amount=command.tax_amount,
            total_amount=command.total_amount,
            irpf_amount=command.irpf_amount,
            is_test=is_test,
            balance_ok=balance_ok,
            snapshot=snapshot,
            confirmed_by=identity.user_id,
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

    # Alimenta el supplier master del tenant (S2.8) EN LA MISMA transacción (sesión inyectada): la
    # próxima verificación de ese CIF acertará por L2. El CIF ya pasó L1 (verify no lo marcó
    # `invalid`), así que `record_confirmation` no rechaza.
    await record_confirmation(
        identity.tenant_id,
        command.counterparty_tax_id or "",
        command.counterparty_name or "",
        session=identity.session,
    )
    return invoice_id


def _diff(extraction: ExtractionRecord, command: ConfirmCommand) -> list[Correction]:
    """Correcciones = diff del body confirmado contra el baseline del OCR (S2.3)."""
    baseline = BaselineFields(
        issue_date=extraction.issue_date,
        total_amount=extraction.total_amount,
        net_amount=extraction.net_amount,
        tax_amount=extraction.tax_amount,
        counterparty_tax_id=extraction.counterparty_tax_id,
        counterparty_name=extraction.counterparty_name,
        tax_lines=_tax_line_fields(_extraction_tax_lines(extraction)),
    )
    confirmed = ConfirmedFields(
        issue_date=command.issue_date,
        total_amount=command.total_amount,
        net_amount=command.net_amount,
        tax_amount=command.tax_amount,
        counterparty_tax_id=command.counterparty_tax_id,
        counterparty_name=command.counterparty_name,
        tax_lines=_tax_line_fields(_command_tax_lines(command)),
    )
    return diff_corrections(baseline, confirmed)


def _tax_line_fields(lines: list[TaxLine]) -> tuple[TaxLineFields, ...]:
    """Adapta los tramos internos (`TaxLine`) al tipo del diff (`TaxLineFields`)."""
    return tuple(
        TaxLineFields(iva_pct=line.iva_pct, base=line.base, cuota=line.cuota) for line in lines
    )


def _snapshot(
    command: ConfirmCommand, verdict: CounterpartyVerdict, balance_ok: bool | None
) -> dict[str, object]:
    """Snapshot append-only de lo confirmado (datos + aceptación) para la traza (audit_log)."""
    return {
        "direction": command.direction,
        "issue_date": _iso(command.issue_date),
        "counterparty_tax_id": command.counterparty_tax_id,
        "counterparty_name": command.counterparty_name,
        "counterparty_cif_status": verdict.status,
        "net_amount": _num(command.net_amount),
        "tax_amount": _num(command.tax_amount),
        "total_amount": _num(command.total_amount),
        "irpf_amount": _num(command.irpf_amount),
        "tax_lines": [
            {"iva_pct": _num(line.iva_pct), "base": _num(line.base), "cuota": _num(line.cuota)}
            for line in command.tax_lines
        ],
        "responsibility_accepted": command.responsibility_accepted,
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
