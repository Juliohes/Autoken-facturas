"""Endpoint HTTP del contexto `companies` (S1.6): lista de empresas del contexto.

Capa HTTP fina: traduce la petición a una lectura (`companies.repository`) y su resultado a la
respuesta. Restringido a `tenant_admin` por el portero de roles (`require_roles`); qué empresas se
ven lo decide la RLS según el contexto que fijó `current_identity`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from companies import repository
from identity.authz import require_roles
from identity.dependencies import AuthContext
from tenancy.constants import Role

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanyOut(BaseModel):
    """Empresa en la respuesta del listado."""

    id: UUID
    name: str
    cif: str
    status: str


@router.get("")
async def list_companies(
    identity: Annotated[AuthContext, Depends(require_roles(Role.TENANT_ADMIN))],
) -> list[CompanyOut]:
    """Lista las empresas de la asesoría (solo `tenant_admin`; la RLS acota lo visible)."""
    rows = await repository.list_companies(identity.session)
    return [CompanyOut(id=row.id, name=row.name, cif=row.cif, status=row.status) for row in rows]
