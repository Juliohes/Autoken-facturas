"""Capa de base de datos: `Base` de los modelos, engine/sesión async y contexto de tenant.

El aislamiento multi-tenant lo garantiza la RLS de Postgres (ADR-0001): la API se conecta con el
rol runtime restringido y, en cada transacción, fija las variables de sesión `app.tenant_id` y
`app.company_id` con `SET LOCAL`. `tenant_session` es el único punto que las fija, para que ninguna
consulta escape del contexto del tenant. Ver spec `docs/specs/S1.1-tenancy-core-rls.md`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from shared.config import get_settings


class Base(DeclarativeBase):
    """Base declarativa común a todos los modelos ORM."""


_engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(
    tenant_id: UUID, company_id: UUID | None = None
) -> AsyncIterator[AsyncSession]:
    """Sesión dentro de una transacción con el contexto de tenant fijado por `SET LOCAL`.

    `company_id` a `None` = contexto de asesoría (ve todo el tenant). Fijado = contexto de una
    empresa (ve solo esa). Las variables viven solo en la transacción; no fugan entre peticiones.
    """
    async with _session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        if company_id is not None:
            await session.execute(
                text("SELECT set_config('app.company_id', :cid, true)"),
                {"cid": str(company_id)},
            )
        yield session
