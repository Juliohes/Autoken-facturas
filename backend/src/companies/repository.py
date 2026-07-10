"""Acceso a datos del contexto `companies`: el SQL de `companies` vive aquí, no en el router.

La sesión llega ya abierta en el contexto de aislamiento por `current_identity` (S1.6): la RLS de
Postgres (ADR-0001) decide qué filas se ven y se escriben. En contexto de asesoría (`tenant_admin`,
sin `app.company_id`) se ven todas las empresas del tenant; en contexto de empresa, solo la propia.
El `tenant_id` de las escrituras NO viaja por parámetro: se toma de `app.tenant_id` (la misma fuente
que la RLS), de modo que ninguna fila puede crearse fuera del tenant de la petición.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tenancy.constants import CompanyStatus

# `tenant_id` de las escrituras derivado del contexto de la sesión (coherente con la RLS).
_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


@dataclass(frozen=True)
class CompanyRow:
    """Datos públicos de una empresa para el listado."""

    id: UUID
    name: str
    cif: str
    status: str


@dataclass(frozen=True)
class CompanyRecord:
    """Empresa completa (incluye `notes`), para operaciones de escritura y lectura por id."""

    id: UUID
    name: str
    cif: str
    status: str
    notes: str | None


async def list_companies(session: AsyncSession) -> list[CompanyRow]:
    """Lista las empresas visibles en el contexto de la sesión, por nombre (la RLS acota)."""
    rows = (
        await session.execute(text("SELECT id, name, cif, status FROM companies ORDER BY name"))
    ).all()
    return [CompanyRow(id=r.id, name=r.name, cif=r.cif, status=r.status) for r in rows]


async def get_company(session: AsyncSession, company_id: UUID) -> CompanyRecord | None:
    """Lee una empresa por id dentro del contexto (la RLS oculta las de otro tenant -> `None`)."""
    row = (
        await session.execute(
            text("SELECT id, name, cif, status, notes FROM companies WHERE id = :id"),
            {"id": str(company_id)},
        )
    ).first()
    if row is None:
        return None
    return CompanyRecord(id=row.id, name=row.name, cif=row.cif, status=row.status, notes=row.notes)


async def get_company_by_cif(session: AsyncSession, cif: str) -> CompanyRecord | None:
    """Lee una empresa por su CIF canónico dentro del contexto (RLS oculta las de otro tenant).

    La usa el registro con aprobación (S1.4, regla 1-A): si el CIF ya existe en la asesoría, el
    usuario se vincula a esa empresa en vez de crear otra. Devuelve `None` si no hay ninguna.
    """
    row = (
        await session.execute(
            text("SELECT id, name, cif, status, notes FROM companies WHERE cif = :cif"),
            {"cif": cif},
        )
    ).first()
    if row is None:
        return None
    return CompanyRecord(id=row.id, name=row.name, cif=row.cif, status=row.status, notes=row.notes)


async def cif_exists(session: AsyncSession, cif: str, *, exclude_id: UUID | None = None) -> bool:
    """True si el `cif` ya existe en el tenant (opcionalmente excluyendo una empresa, para editar).

    La unicidad de negocio se comprueba aquí (SELECT acotado por RLS) en vez de dejar reventar el
    UNIQUE `(tenant_id, cif)`: dentro de la transacción única de la petición un INSERT fallido la
    abortaría entera, lo que rompería el éxito parcial de la importación. El UNIQUE del esquema es
    la red de seguridad última.
    """
    sql = "SELECT 1 FROM companies WHERE cif = :cif"
    params: dict[str, str] = {"cif": cif}
    if exclude_id is not None:
        sql += " AND id <> :exclude_id"
        params["exclude_id"] = str(exclude_id)
    row = (await session.execute(text(sql + " LIMIT 1"), params)).first()
    return row is not None


async def existing_cifs(session: AsyncSession) -> set[str]:
    """Conjunto de CIF ya presentes en el tenant (para resolver duplicados de la importación)."""
    rows = (await session.execute(text("SELECT cif FROM companies"))).all()
    return {r.cif for r in rows}


async def insert_company(
    session: AsyncSession, *, name: str, cif: str, status: str, notes: str | None
) -> CompanyRecord:
    """Inserta una empresa en el tenant del contexto y devuelve la fila creada."""
    row = (
        await session.execute(
            text(
                f"INSERT INTO companies (tenant_id, name, cif, status, notes) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, :name, :cif, :status, :notes) "
                f"RETURNING id, name, cif, status, notes"
            ),
            {"name": name, "cif": cif, "status": status, "notes": notes},
        )
    ).one()
    return CompanyRecord(id=row.id, name=row.name, cif=row.cif, status=row.status, notes=row.notes)


async def update_company(
    session: AsyncSession,
    company_id: UUID,
    *,
    name: str,
    cif: str,
    status: str,
    notes: str | None,
) -> CompanyRecord:
    """Actualiza todos los campos editables de una empresa del contexto y devuelve la fila."""
    row = (
        await session.execute(
            text(
                "UPDATE companies SET name = :name, cif = :cif, status = :status, notes = :notes "
                "WHERE id = :id RETURNING id, name, cif, status, notes"
            ),
            {
                "id": str(company_id),
                "name": name,
                "cif": cif,
                "status": status,
                "notes": notes,
            },
        )
    ).one()
    return CompanyRecord(id=row.id, name=row.name, cif=row.cif, status=row.status, notes=row.notes)


async def activate_pending_company(session: AsyncSession, company_id: UUID) -> None:
    """Activa una empresa PENDIENTE del contexto (aprobación de un registro, S1.4 regla 3-A).

    Solo toca la fila si está `pending`: una empresa ya `active` (vínculo 1-A a una existente) se
    deja igual. El SQL de `companies` vive aquí (simetría con el resto de escrituras del contexto),
    no en `identity`; la RLS impide tocar empresas de otro tenant.
    """
    await session.execute(
        text("UPDATE companies SET status = :active WHERE id = :id AND status = :pending"),
        {
            "active": CompanyStatus.ACTIVE.value,
            "pending": CompanyStatus.PENDING.value,
            "id": str(company_id),
        },
    )


async def delete_company(session: AsyncSession, company_id: UUID) -> None:
    """Borra una empresa del contexto (la RLS impide tocar las de otro tenant)."""
    await session.execute(text("DELETE FROM companies WHERE id = :id"), {"id": str(company_id)})


async def count_memberships(session: AsyncSession, company_id: UUID) -> int:
    """Número de usuarios vinculados (memberships) a la empresa, para el borrado seguro."""
    row = (
        await session.execute(
            text("SELECT count(*) AS n FROM memberships WHERE company_id = :id"),
            {"id": str(company_id)},
        )
    ).one()
    return int(row.n)
