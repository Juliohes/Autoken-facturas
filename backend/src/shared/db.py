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
        # `hide_parameters=True` (S5.2, hallazgo de auditoría de seguridad): sin esto, cualquier
        # `StatementError`/`DBAPIError` de SQLAlchemy incluye en su mensaje los bind params reales
        # de la sentencia — para las consultas que cifran/descifran (`pgp_sym_encrypt`/
        # `pgp_sym_decrypt`), eso es la CLAVE de cifrado del tenant en texto plano dentro del propio
        # mensaje de la excepción, que acaba en logs (`logger.exception`) y en Sentry si se activa
        # (S5.6). Se oculta siempre, no solo en producción: un `.env` de desarrollo también deriva
        # claves reales si `DB_ENCRYPTION_MASTER_KEY` está puesta.
        settings = get_settings()
        # `pool_size`/`max_overflow` (S5.5, hallazgo real de la prueba de carga): sin fijarlos,
        # el default de SQLAlchemy (5 + 10 = 15 conexiones simultáneas) se agota bajo una carga de
        # subida de facturas moderadamente concurrente — ver `shared.config.Settings.db_pool_size`.
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            hide_parameters=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
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
async def platform_session() -> AsyncIterator[AsyncSession]:
    """Sesión transaccional SIN contexto de tenant, para operaciones de `platform_admin` (S4.1).

    A diferencia de `session()` (sin transacción explícita, pensada para lecturas puntuales como
    `resolve_tenant`), esta SÍ abre una transacción real (commit al salir sin error, rollback si hay
    excepción): las escrituras de plataforma (alta de tenant vía la función `SECURITY DEFINER`
    `create_tenant`) necesitan confirmarse de verdad. Sin `SET LOCAL` de `app.tenant_id`/
    `app.company_id`: un `platform_admin` no tiene tenant (S1.3); las funciones que llama ya saltan
    la RLS por sí mismas (`BYPASSRLS` del rol propietario, no de la sesión del rol runtime).

    **No usar para leer/escribir tablas de negocio directamente** (`companies`, `invoices`...): sin
    contexto de tenant, la RLS de esas tablas falla cerrado (0 filas en `SELECT`, violación de
    política en `INSERT`/`UPDATE`), así que un mal uso no fuga datos entre tenants, pero sí produce
    un bug silencioso difícil de depurar. Esta sesión es solo para invocar funciones `SECURITY
    DEFINER` de plataforma ya acotadas (`create_tenant`, `list_tenants`...), nunca SQL de negocio
    libre.
    """
    async with _get_sessionmaker()() as db_session, db_session.begin():
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
