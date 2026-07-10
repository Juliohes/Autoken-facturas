"""Lógica de dominio del contexto `companies`: reglas de negocio del CRUD (fuera del router).

El router HTTP es fino: traduce peticiones a estas operaciones y sus excepciones de dominio a
códigos HTTP. Aquí viven las reglas: identificador fiscal válido (dígito de control), unicidad por
asesoría, borrado seguro y estado. La persistencia se delega en `repository`; la validación del CIF
en `ocr.verification`; la traza en `shared.audit`. La importación del Excel vive en `importer.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from companies import repository
from companies.repository import CompanyRecord
from ocr.verification import normalize_tax_id, validate_tax_id
from shared.audit import write_audit
from shared.integrity import violates_unique_constraint
from tenancy.constants import CompanyStatus

# Entidad y acciones de auditoría del contexto `companies`, en constantes (no literales sueltos):
# las comparte el CRUD (`service`) y la importación (`importer`) para que la traza sea coherente.
_AUDIT_ENTITY = "company"
AUDIT_ACTION_CREATE = "company.create"
AUDIT_ACTION_UPDATE = "company.update"
AUDIT_ACTION_DELETE = "company.delete"

# Nombre del UNIQUE `(tenant_id, cif)` del esquema (migración 0001): red de seguridad última de la
# unicidad, más allá del pre-check `cif_exists`. Se usa para traducir su violación a `DuplicateCif`.
_CIF_UNIQUE_CONSTRAINT = "companies_tenant_cif_unique"


def is_cif_unique_violation(exc: IntegrityError) -> bool:
    """True si la `IntegrityError` viene del UNIQUE `(tenant_id, cif)` (y no de otra restricción).

    Distingue el choque de CIF de cualquier otra violación de integridad para no enmascararla:
    solo la del UNIQUE de empresa se traduce a `DuplicateCif` (409); el resto se deja propagar.
    """
    return violates_unique_constraint(exc, _CIF_UNIQUE_CONSTRAINT)


class CompanyError(Exception):
    """Raíz de los errores de dominio del contexto `companies`."""


class InvalidTaxId(CompanyError):
    """El identificador fiscal no supera la validación estructural/de dígito de control (-> 422)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DuplicateCif(CompanyError):
    """Ya existe una empresa con ese CIF en la asesoría (unicidad `(tenant_id, cif)`) (-> 409)."""


class CompanyNotFound(CompanyError):
    """La empresa no existe en el contexto de la petición (inexistente u otro tenant) (-> 404)."""


class CompanyHasMembers(CompanyError):
    """La empresa tiene usuarios (memberships): no se borra para proteger el histórico (-> 409)."""


def validated_cif(raw: str | None) -> str:
    """Devuelve la forma canónica del CIF/NIF si es válido; si no, lanza `InvalidTaxId`.

    Reutiliza el validador "tipo DNI" (`ocr.verification`): normaliza y comprueba el dígito de
    control de NIF/NIE/CIF. La forma canónica (mayúsculas, sin separadores) es la que se persiste,
    para que la unicidad no dependa del formato con el que se teclee el identificador.
    """
    result = validate_tax_id(raw)
    if not result.valid:
        raise InvalidTaxId(result.reason)
    return normalize_tax_id(raw)


async def persist_new_company(
    session: AsyncSession,
    *,
    actor_id: UUID,
    name: str,
    canonical_cif: str,
    notes: str | None = None,
) -> CompanyRecord:
    """Inserta la empresa canónica (`active`) y deja su traza `company.create`; devuelve la fila.

    Centraliza el invariante de "empresa nueva" (insert + audit atómicos) que comparten el alta
    unitaria (`create_company`) y el bucle del importador. NO comprueba unicidad: la decide quien
    llama (pre-check por CIF ya conocido); el UNIQUE `(tenant_id, cif)` es la red última.
    """
    record = await repository.insert_company(
        session, name=name, cif=canonical_cif, status=CompanyStatus.ACTIVE.value, notes=notes
    )
    await write_audit(
        session,
        actor_id=actor_id,
        action=AUDIT_ACTION_CREATE,
        entity=_AUDIT_ENTITY,
        entity_id=record.id,
    )
    return record


async def create_company(
    session: AsyncSession, *, actor_id: UUID, name: str, cif: str, notes: str | None
) -> CompanyRecord:
    """Da de alta una empresa `active`: valida el CIF, exige unicidad y deja traza de auditoría.

    La unicidad se resuelve con un pre-check (`cif_exists`) como fast-path; pero dos altas
    concurrentes pueden pasarlo ambas y chocar en el UNIQUE `(tenant_id, cif)`: se captura esa
    `IntegrityError` y se traduce también a `DuplicateCif` (409), en vez de dejar escapar un 500.
    """
    canonical = validated_cif(cif)
    if await repository.cif_exists(session, canonical):
        raise DuplicateCif()
    try:
        return await persist_new_company(
            session, actor_id=actor_id, name=name, canonical_cif=canonical, notes=notes
        )
    except IntegrityError as exc:
        if is_cif_unique_violation(exc):
            raise DuplicateCif() from exc
        raise


async def update_company(
    session: AsyncSession,
    *,
    actor_id: UUID,
    company_id: UUID,
    changes: Mapping[str, Any],
) -> CompanyRecord:
    """Edita los campos presentes en `changes`; revalida el CIF si cambia y respeta la unicidad.

    `changes` contiene solo los campos enviados (patch parcial). Si incluye `cif`, se revalida
    (422 si es inválido) y se comprueba que no choque con otra empresa de la asesoría (409). Una
    empresa fuera del contexto (otro tenant) no existe aquí: `CompanyNotFound` (404).
    """
    current = await repository.get_company(session, company_id)
    if current is None:
        raise CompanyNotFound()

    if "cif" in changes:
        cif = validated_cif(changes["cif"])
        if await repository.cif_exists(session, cif, exclude_id=company_id):
            raise DuplicateCif()
    else:
        cif = current.cif

    name = changes.get("name", current.name)
    status = changes.get("status", current.status)
    notes = changes.get("notes", current.notes)

    record = await repository.update_company(
        session, company_id, name=name, cif=cif, status=status, notes=notes
    )
    await write_audit(
        session,
        actor_id=actor_id,
        action=AUDIT_ACTION_UPDATE,
        entity=_AUDIT_ENTITY,
        entity_id=record.id,
    )
    return record


async def delete_company(session: AsyncSession, *, actor_id: UUID, company_id: UUID) -> None:
    """Borra una empresa sin dependencias; con usuarios (memberships) lanza `CompanyHasMembers`."""
    current = await repository.get_company(session, company_id)
    if current is None:
        raise CompanyNotFound()
    if await repository.count_memberships(session, company_id) > 0:
        raise CompanyHasMembers()
    await repository.delete_company(session, company_id)
    await write_audit(
        session,
        actor_id=actor_id,
        action=AUDIT_ACTION_DELETE,
        entity=_AUDIT_ENTITY,
        entity_id=company_id,
    )
