"""Lógica de dominio del contexto `companies`: reglas de negocio del CRUD (fuera del router).

El router HTTP es fino: traduce peticiones a estas operaciones y sus excepciones de dominio a
códigos HTTP. Aquí viven las reglas: identificador fiscal válido (dígito de control), unicidad por
asesoría, borrado seguro y estado. La persistencia se delega en `repository`; la validación del CIF
en `shared.tax_id`; la traza en `shared.audit`. La importación del Excel vive en `importer.py`.

Cifrado en reposo (S5.2): este módulo es el único que conoce la clave maestra (`settings`) y deriva
la clave de cifrado/índice de CADA tenant (`shared.encryption`) — el repositorio nunca deriva
claves, solo las usa. `tenant_id` se recibe explícito (no se lee de `app.tenant_id` en Python: esa
variable de sesión solo la ve Postgres) para poder derivar la clave ANTES de tocar la BD.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from companies import repository
from companies.repository import CompanyRecord
from shared.audit import write_audit
from shared.config import Settings
from shared.encryption import tenant_encryption_key as tenant_encryption_key
from shared.encryption import tenant_tax_id_blind_index
from shared.integrity import violates_unique_constraint
from shared.tax_id import normalize_tax_id, validate_tax_id
from tenancy.constants import CompanyStatus

# `tenant_encryption_key` se re-exporta tal cual (ya llega importada con el nombre correcto): los
# importadores existentes (`from companies.service import tenant_encryption_key as ...`) siguen
# funcionando sin cambios. La derivación de clave/índice vive ahora en `shared.encryption` (fuente
# única, spec §4/ADR-0018); `companies` fue el contexto de referencia, no el dueño de la lógica.


def cif_blind_index(settings: Settings, tenant_id: UUID, canonical_cif: str) -> str:
    """Índice ciego del CIF ya canónico de este tenant (para `WHERE`/`UNIQUE` sin descifrar).

    `companies.cif` es `NOT NULL` (siempre validado por `validated_cif` antes de llegar aquí, nunca
    vacío): a diferencia de `shared.encryption.tenant_tax_id_blind_index` (genérica, admite un CIF
    ausente en facturas/contrapartes), esta envoltura mantiene el contrato no-opcional del contexto.
    """
    result = tenant_tax_id_blind_index(settings, tenant_id, canonical_cif)
    assert result is not None  # canonical_cif ya viene validado no vacío (validated_cif)
    return result


async def list_companies(
    session: AsyncSession, *, tenant_id: UUID, settings: Settings
) -> list[repository.CompanyRow]:
    """Lista las empresas de la asesoría (solo lectura): deriva la clave aquí, nunca en el router
    (hallazgo de auditoría — este era, precisamente, el módulo de referencia del patrón)."""
    encryption_key = tenant_encryption_key(settings, tenant_id)
    return await repository.list_companies(session, encryption_key=encryption_key)


# Entidad y acciones de auditoría del contexto `companies`, en constantes (no literales sueltos):
# las comparte el CRUD (`service`) y la importación (`importer`) para que la traza sea coherente.
_AUDIT_ENTITY = "company"
AUDIT_ACTION_CREATE = "company.create"
AUDIT_ACTION_UPDATE = "company.update"
AUDIT_ACTION_DELETE = "company.delete"

# Nombre del UNIQUE `(tenant_id, cif_blind_index)` del esquema (migración 0020, S5.2): red de
# seguridad última de la unicidad, más allá del pre-check `cif_blind_index_exists`.
_CIF_UNIQUE_CONSTRAINT = "companies_tenant_cif_blind_index_unique"


def is_cif_unique_violation(exc: IntegrityError) -> bool:
    """True si la `IntegrityError` viene del UNIQUE `(tenant_id, cif_blind_index)` (y no de otra
    restricción).

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
    """Ya existe una empresa con ese CIF en la asesoría (unicidad por índice ciego) (-> 409)."""


class CompanyNotFound(CompanyError):
    """La empresa no existe en el contexto de la petición (inexistente u otro tenant) (-> 404)."""


class CompanyHasMembers(CompanyError):
    """La empresa tiene usuarios (memberships): no se borra para proteger el histórico (-> 409)."""


def validated_cif(raw: str | None) -> str:
    """Devuelve la forma canónica del CIF/NIF si es válido; si no, lanza `InvalidTaxId`.

    Reutiliza el validador "tipo DNI" (`shared.tax_id`): normaliza y comprueba el dígito de
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
    tenant_id: UUID,
    settings: Settings,
    name: str,
    canonical_cif: str,
    notes: str | None = None,
) -> CompanyRecord:
    """Inserta la empresa canónica (`active`) y deja su traza `company.create`; devuelve la fila.

    Centraliza el invariante de "empresa nueva" (insert + audit atómicos) que comparten el alta
    unitaria (`create_company`) y el bucle del importador. NO comprueba unicidad: la decide quien
    llama (pre-check por CIF ya conocido); el UNIQUE `(tenant_id, cif_blind_index)` es la red
    última.
    """
    record = await repository.insert_company(
        session,
        name=name,
        cif=canonical_cif,
        cif_blind_index=cif_blind_index(settings, tenant_id, canonical_cif),
        status=CompanyStatus.ACTIVE.value,
        notes=notes,
        encryption_key=tenant_encryption_key(settings, tenant_id),
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
    session: AsyncSession,
    *,
    actor_id: UUID,
    tenant_id: UUID,
    settings: Settings,
    name: str,
    cif: str,
    notes: str | None,
) -> CompanyRecord:
    """Da de alta una empresa `active`: valida el CIF, exige unicidad y deja traza de auditoría.

    La unicidad se resuelve con un pre-check (`cif_blind_index_exists`) como fast-path; pero dos
    altas concurrentes pueden pasarlo ambas y chocar en el UNIQUE `(tenant_id, cif_blind_index)`: se
    captura esa `IntegrityError` y se traduce también a `DuplicateCif` (409), en vez de dejar
    escapar un 500.
    """
    canonical = validated_cif(cif)
    idx = cif_blind_index(settings, tenant_id, canonical)
    if await repository.cif_blind_index_exists(session, idx):
        raise DuplicateCif()
    try:
        return await persist_new_company(
            session,
            actor_id=actor_id,
            tenant_id=tenant_id,
            settings=settings,
            name=name,
            canonical_cif=canonical,
            notes=notes,
        )
    except IntegrityError as exc:
        if is_cif_unique_violation(exc):
            raise DuplicateCif() from exc
        raise


async def update_company(
    session: AsyncSession,
    *,
    actor_id: UUID,
    tenant_id: UUID,
    settings: Settings,
    company_id: UUID,
    changes: Mapping[str, Any],
) -> CompanyRecord:
    """Edita los campos presentes en `changes`; revalida el CIF si cambia y respeta la unicidad.

    `changes` contiene solo los campos enviados (patch parcial). Si incluye `cif`, se revalida
    (422 si es inválido) y se comprueba que no choque con otra empresa de la asesoría (409). Una
    empresa fuera del contexto (otro tenant) no existe aquí: `CompanyNotFound` (404).
    """
    encryption_key = tenant_encryption_key(settings, tenant_id)
    current = await repository.get_company(session, company_id, encryption_key=encryption_key)
    if current is None:
        raise CompanyNotFound()

    if "cif" in changes:
        cif = validated_cif(changes["cif"])
        idx = cif_blind_index(settings, tenant_id, cif)
        if await repository.cif_blind_index_exists(session, idx, exclude_id=company_id):
            raise DuplicateCif()
    else:
        cif = current.cif
        idx = cif_blind_index(settings, tenant_id, cif)

    name = changes.get("name", current.name)
    status = changes.get("status", current.status)
    notes = changes.get("notes", current.notes)

    record = await repository.update_company(
        session,
        company_id,
        name=name,
        cif=cif,
        cif_blind_index=idx,
        status=status,
        notes=notes,
        encryption_key=encryption_key,
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
    """Borra una empresa sin dependencias; con usuarios (memberships) lanza `CompanyHasMembers`.

    No necesita la clave de cifrado: no lee ni escribe `cif`/`name`, solo comprueba existencia por
    id (`company_exists`, sin descifrar nada) y borra.
    """
    if not await repository.company_exists(session, company_id):
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
