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
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from shared.config import get_settings


class Base(DeclarativeBase):
    """Base declarativa común a todos los modelos ORM."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Factoría de sesiones perezosa y reutilizada (el engine no se crea en import-time).

    Perezosa para no acoplar el import a `DATABASE_URL` ni crear el pool antes del fork de workers o
    del event loop de los tests. Se reutiliza (no se crea una por llamada).
    """
    global _engine, _sessionmaker
    if _sessionmaker is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


def get_engine() -> AsyncEngine:
    """Devuelve el engine async de la app (perezoso y reutilizado).

    Fuerza la creación perezosa vía `_get_sessionmaker` y expone el engine para chequeos de
    arranque que necesitan la conexión REAL de la app (p. ej. el guardarraíl de RLS, ADR-0014).
    """
    _get_sessionmaker()
    if _engine is None:  # pragma: no cover - `_get_sessionmaker` siempre lo crea
        raise RuntimeError("el engine no se inicializó")
    return _engine


async def dispose_engine() -> None:
    """Cierra el engine y su pool (lifespan de la app; tests tras cambiar `DATABASE_URL`)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    """Sesión SIN contexto de tenant (RLS activa: 0 filas en tablas de negocio).

    Solo para operaciones que no dependen de un tenant: p. ej. llamar a `resolve_tenant(slug)`
    (SECURITY DEFINER) durante la resolución del subdominio, antes de tener `app.tenant_id`.
    """
    async with _get_sessionmaker()() as db_session:
        yield db_session


@asynccontextmanager
async def tenant_session(
    tenant_id: UUID, company_id: UUID | None = None
) -> AsyncIterator[AsyncSession]:
    """Sesión dentro de una transacción con el contexto de tenant fijado por `SET LOCAL`.

    `company_id` a `None` = contexto de asesoría (ve todo el tenant). Fijado = contexto de una
    empresa (ve solo esa). Las variables viven solo en la transacción; no fugan entre peticiones.
    """
    async with _get_sessionmaker()() as session, session.begin():
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
