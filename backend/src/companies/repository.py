"""Acceso a datos del contexto `companies`: el SQL de `companies` vive aquí, no en el router.

La sesión llega ya abierta en el contexto de aislamiento por `current_identity` (S1.6): la RLS de
Postgres (ADR-0001) decide qué filas se ven y se escriben. En contexto de asesoría (`tenant_admin`,
sin `app.company_id`) se ven todas las empresas del tenant; en contexto de empresa, solo la propia.
El `tenant_id` de las escrituras NO viaja por parámetro: se toma de `app.tenant_id` (la misma fuente
que la RLS), de modo que ninguna fila puede crearse fuera del tenant de la petición.

`cif`/`name` viven cifrados en Postgres desde S5.2 (`pgp_sym_encrypt`/`pgp_sym_decrypt`, clave por
tenant derivada — nunca guardada). Cada función que lee/escribe esas columnas recibe la clave ya
derivada (`encryption_key`) como parámetro: el repositorio no sabe de dónde sale la clave (eso es de
`companies.service`), solo la usa. La igualdad/unicidad por CIF se resuelve por `cif_blind_index`
(HMAC determinista), nunca comparando el cifrado en sí (no determinista, spec S5.2 §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tenancy.constants import CompanyStatus

# `tenant_id` de las escrituras derivado del contexto de la sesión (coherente con la RLS).
_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_DECRYPTED_COLUMNS = (
    "pgp_sym_decrypt(name, :key)::text AS name, pgp_sym_decrypt(cif, :key)::text AS cif"
)


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


async def list_companies(session: AsyncSession, *, encryption_key: str) -> list[CompanyRow]:
    """Lista las empresas visibles en el contexto de la sesión (la RLS acota), por id de creación.

    Ya no se puede ordenar por `name` en SQL (cifrado, sin índice ciego de nombre, spec S5.2 §0):
    se ordena por `id` (orden estable, no revela nada) y el cliente/lista pequeña la reordena si
    hace falta visualmente.
    """
    rows = (
        await session.execute(
            text(f"SELECT id, {_DECRYPTED_COLUMNS}, status FROM companies ORDER BY id"),
            {"key": encryption_key},
        )
    ).all()
    return [CompanyRow(id=r.id, name=r.name, cif=r.cif, status=r.status) for r in rows]


async def get_company(
    session: AsyncSession, company_id: UUID, *, encryption_key: str
) -> CompanyRecord | None:
    """Lee una empresa por id dentro del contexto (la RLS oculta las de otro tenant -> `None`)."""
    row = (
        await session.execute(
            text(f"SELECT id, {_DECRYPTED_COLUMNS}, status, notes FROM companies WHERE id = :id"),
            {"id": str(company_id), "key": encryption_key},
        )
    ).first()
    if row is None:
        return None
    return CompanyRecord(id=row.id, name=row.name, cif=row.cif, status=row.status, notes=row.notes)


async def get_company_by_cif_blind_index(
    session: AsyncSession, cif_blind_index: str, *, encryption_key: str
) -> CompanyRecord | None:
    """Lee una empresa por el índice ciego de su CIF canónico (RLS oculta las de otro tenant).

    La usa el registro con aprobación (S1.4, regla 1-A): si el CIF ya existe en la asesoría, el
    usuario se vincula a esa empresa en vez de crear otra. Devuelve `None` si no hay ninguna.
    `cif_blind_index` ya viene calculado por el llamador (`companies.service`, que conoce la clave
    de índice del tenant); este repositorio nunca deriva claves.
    """
    row = (
        await session.execute(
            text(
                f"SELECT id, {_DECRYPTED_COLUMNS}, status, notes FROM companies "
                f"WHERE cif_blind_index = :idx"
            ),
            {"idx": cif_blind_index, "key": encryption_key},
        )
    ).first()
    if row is None:
        return None
    return CompanyRecord(id=row.id, name=row.name, cif=row.cif, status=row.status, notes=row.notes)


async def cif_blind_index_exists(
    session: AsyncSession, cif_blind_index: str, *, exclude_id: UUID | None = None
) -> bool:
    """True si el índice ciego del `cif` ya existe en el tenant (opcionalmente excluyendo una
    empresa, para editar).

    La unicidad de negocio se comprueba aquí (SELECT acotado por RLS) en vez de dejar reventar el
    UNIQUE `(tenant_id, cif_blind_index)`: dentro de la transacción única de la petición un INSERT
    fallido la abortaría entera, lo que rompería el éxito parcial de la importación. El UNIQUE del
    esquema es la red de seguridad última.
    """
    sql = "SELECT 1 FROM companies WHERE cif_blind_index = :idx"
    params: dict[str, str] = {"idx": cif_blind_index}
    if exclude_id is not None:
        sql += " AND id <> :exclude_id"
        params["exclude_id"] = str(exclude_id)
    row = (await session.execute(text(sql + " LIMIT 1"), params)).first()
    return row is not None


async def existing_cifs(session: AsyncSession, *, encryption_key: str) -> set[str]:
    """Conjunto de CIF (descifrados) ya presentes en el tenant, para resolver duplicados de la
    importación en memoria antes de tocar la BD."""
    rows = (
        await session.execute(
            text("SELECT pgp_sym_decrypt(cif, :key)::text AS cif FROM companies"),
            {"key": encryption_key},
        )
    ).all()
    return {r.cif for r in rows}


async def insert_company(
    session: AsyncSession,
    *,
    name: str,
    cif: str,
    cif_blind_index: str,
    status: str,
    notes: str | None,
    encryption_key: str,
) -> CompanyRecord:
    """Inserta una empresa en el tenant del contexto y devuelve la fila creada (ya descifrada)."""
    row = (
        await session.execute(
            text(
                f"INSERT INTO companies "
                f"(tenant_id, name, cif, cif_blind_index, status, notes) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, pgp_sym_encrypt(:name, :key), "
                f" pgp_sym_encrypt(:cif, :key), :cif_blind_index, :status, :notes) "
                f"RETURNING id, {_DECRYPTED_COLUMNS}, status, notes"
            ),
            {
                "name": name,
                "cif": cif,
                "cif_blind_index": cif_blind_index,
                "status": status,
                "notes": notes,
                "key": encryption_key,
            },
        )
    ).one()
    return CompanyRecord(id=row.id, name=row.name, cif=row.cif, status=row.status, notes=row.notes)


async def update_company(
    session: AsyncSession,
    company_id: UUID,
    *,
    name: str,
    cif: str,
    cif_blind_index: str,
    status: str,
    notes: str | None,
    encryption_key: str,
) -> CompanyRecord:
    """Actualiza todos los campos editables de una empresa del contexto y devuelve la fila."""
    row = (
        await session.execute(
            text(
                "UPDATE companies SET name = pgp_sym_encrypt(:name, :key), "
                "cif = pgp_sym_encrypt(:cif, :key), cif_blind_index = :cif_blind_index, "
                "status = :status, notes = :notes WHERE id = :id "
                f"RETURNING id, {_DECRYPTED_COLUMNS}, status, notes"
            ),
            {
                "id": str(company_id),
                "name": name,
                "cif": cif,
                "cif_blind_index": cif_blind_index,
                "status": status,
                "notes": notes,
                "key": encryption_key,
            },
        )
    ).one()
    return CompanyRecord(id=row.id, name=row.name, cif=row.cif, status=row.status, notes=row.notes)


async def company_exists(session: AsyncSession, company_id: UUID) -> bool:
    """True si la empresa existe en el contexto (la RLS oculta las de otro tenant).

    No descifra nada (no hace falta la clave del tenant): solo comprueba presencia por id, para el
    borrado (`companies.service.delete_company`), que no necesita leer `cif`/`name`.
    """
    row = (
        await session.execute(
            text("SELECT 1 FROM companies WHERE id = :id"), {"id": str(company_id)}
        )
    ).first()
    return row is not None


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
