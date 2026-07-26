"""Endpoints HTTP del contexto `companies` (S1.5/S1.6): listado + CRUD + importación del Excel.

Capa HTTP **fina**: traduce la petición a una operación de dominio (`companies.service` /
`companies.importer`) y su resultado o su excepción de dominio a la respuesta HTTP. No contiene SQL
ni reglas de negocio. Toda la gestión está restringida a `tenant_admin` por el portero de roles
(`require_roles`, S1.6); qué empresas se ven/afectan lo decide la RLS según el contexto que fijó
`current_identity`.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from companies import importer, repository, service
from identity.authz import require_roles
from identity.dependencies import AuthContext
from shared.config import Settings, get_settings
from tenancy.constants import Role

router = APIRouter(prefix="/companies", tags=["companies"])
SettingsDep = Annotated[Settings, Depends(get_settings)]

# Dependencia común: identidad autenticada y autorizada como `tenant_admin` (gestión de empresas).
TenantAdmin = Annotated[AuthContext, Depends(require_roles(Role.TENANT_ADMIN))]


class CompanyOut(BaseModel):
    """Empresa en la respuesta (alta, edición y listado)."""

    id: UUID
    name: str
    cif: str
    status: str


class CompanyCreate(BaseModel):
    """Cuerpo de `POST /companies`."""

    name: str
    cif: str
    notes: str | None = None


class CompanyUpdate(BaseModel):
    """Cuerpo de `PATCH /companies/{id}` (patch parcial: solo los campos presentes cambian)."""

    name: str | None = None
    cif: str | None = None
    notes: str | None = None
    status: Literal["active", "pending"] | None = None


def _to_out(record: repository.CompanyRow | repository.CompanyRecord) -> CompanyOut:
    """Mapea una fila de empresa (listado o registro completo) al DTO público `CompanyOut`."""
    return CompanyOut(id=record.id, name=record.name, cif=record.cif, status=record.status)


@router.get("")
async def list_companies(identity: TenantAdmin, settings: SettingsDep) -> list[CompanyOut]:
    """Lista las empresas de la asesoría (solo `tenant_admin`; la RLS acota lo visible)."""
    rows = await service.list_companies(
        identity.session, tenant_id=identity.tenant_id, settings=settings
    )
    return [_to_out(row) for row in rows]


@router.post("", status_code=201)
async def create_company(
    identity: TenantAdmin, settings: SettingsDep, body: CompanyCreate
) -> CompanyOut:
    """Da de alta una empresa `active`. CIF inválido -> 422; CIF ya existente -> 409."""
    try:
        record = await service.create_company(
            identity.session,
            actor_id=identity.user_id,
            tenant_id=identity.tenant_id,
            settings=settings,
            name=body.name,
            cif=body.cif,
            notes=body.notes,
        )
    except service.InvalidTaxId as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except service.DuplicateCif as exc:
        raise HTTPException(status_code=409, detail="La empresa ya existe en la asesoría") from exc
    return _to_out(record)


@router.patch("/{company_id}")
async def update_company(
    identity: TenantAdmin, settings: SettingsDep, company_id: UUID, body: CompanyUpdate
) -> CompanyOut:
    """Edita una empresa. CIF inválido -> 422; CIF duplicado -> 409; de otro tenant -> 404."""
    changes = body.model_dump(exclude_unset=True)
    try:
        record = await service.update_company(
            identity.session,
            actor_id=identity.user_id,
            tenant_id=identity.tenant_id,
            settings=settings,
            company_id=company_id,
            changes=changes,
        )
    except service.CompanyNotFound as exc:
        raise HTTPException(status_code=404, detail="Empresa no encontrada") from exc
    except service.InvalidTaxId as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except service.DuplicateCif as exc:
        raise HTTPException(status_code=409, detail="La empresa ya existe en la asesoría") from exc
    return _to_out(record)


@router.delete("/{company_id}", status_code=204)
async def delete_company(identity: TenantAdmin, company_id: UUID) -> None:
    """Borra una empresa sin dependencias. Con usuarios -> 409; de otro tenant -> 404."""
    try:
        await service.delete_company(
            identity.session, actor_id=identity.user_id, company_id=company_id
        )
    except service.CompanyNotFound as exc:
        raise HTTPException(status_code=404, detail="Empresa no encontrada") from exc
    except service.CompanyHasMembers as exc:
        raise HTTPException(
            status_code=409,
            detail="La empresa tiene usuarios asignados: reasígnalos o quítalos antes de borrarla",
        ) from exc


class InvalidRowOut(BaseModel):
    """Fila rechazada en el informe de importación: número de fila (1-based) y motivo."""

    row: int
    reason: str


class DuplicateRowOut(BaseModel):
    """Fila omitida por CIF ya existente en el informe: número de fila (1-based) y CIF."""

    row: int
    cif: str


class ImportReportOut(BaseModel):
    """Informe de la importación del Excel."""

    created: int
    invalid: list[InvalidRowOut]
    duplicates: list[DuplicateRowOut]
    truncated: bool


@router.post("/import")
async def import_companies(
    identity: TenantAdmin, settings: SettingsDep, file: UploadFile
) -> ImportReportOut:
    """Importa un `.xlsx` (multipart `file`). Fichero/columnas inválidos -> 400 controlado.

    Guardarraíles anti-DoS por memoria (fichero compartido por todas las asesorías): se rechaza con
    413 el fichero que supera `companies_import_max_bytes` ANTES de parsearlo (lectura acotada, sin
    materializar un `.xlsx` gigante o zip-bomb en memoria), y el parseo corta a
    `companies_import_max_rows` filas.
    """
    max_bytes = settings.companies_import_max_bytes
    # Lectura acotada: como mucho `max_bytes + 1` bytes en memoria; si sobra, es que excede el tope.
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"El fichero supera el tamaño máximo permitido ({max_bytes} bytes)",
        )
    try:
        report = await importer.import_companies(
            identity.session,
            actor_id=identity.user_id,
            tenant_id=identity.tenant_id,
            settings=settings,
            content=content,
            max_rows=settings.companies_import_max_rows,
        )
    except importer.MalformedFile as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportReportOut(
        created=report.created,
        invalid=[InvalidRowOut(row=r.row, reason=r.reason) for r in report.invalid],
        duplicates=[DuplicateRowOut(row=r.row, cif=r.cif) for r in report.duplicates],
        truncated=report.truncated,
    )
