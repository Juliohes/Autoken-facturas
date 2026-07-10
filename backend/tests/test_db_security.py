"""Test del guardarraíl de arranque: el rol de conexión de la app no puede saltarse la RLS (#50).

Contra un PostgreSQL real y los DOS DSN de test: con el del superusuario (`admin`, que salta la RLS)
el guardarraíl DEBE fallar; con el del rol runtime restringido (`app_async`, NOSUPERUSER/NOBYPASSRLS
que crea la migración 0001) DEBE pasar. Es el control que evita levantar la app con el aislamiento
multi-tenant anulado (ADR-0014). Se marca `isolation` para que el gate bloqueante de CI lo ejercite.
"""

from __future__ import annotations

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from shared.db_security import (
    RlsEnabledWithoutForceError,
    RuntimeRoleCanBypassRlsError,
    assert_runtime_role_cannot_bypass_rls,
)
from tests._dbtest import provision_test_db

pytestmark = pytest.mark.isolation


def _async_url(dsn: str) -> str:
    """DSN `postgresql://` -> `postgresql+asyncpg://` para el engine async de SQLAlchemy."""
    return dsn.replace("postgresql://", "postgresql+asyncpg://")


async def test_superusuario_hace_fallar_el_arranque() -> None:
    """Con el DSN del superusuario (salta la RLS), el guardarraíl aborta el arranque."""
    dsns = await provision_test_db()
    engine = create_async_engine(_async_url(dsns["admin"]))
    try:
        with pytest.raises(RuntimeRoleCanBypassRlsError):
            await assert_runtime_role_cannot_bypass_rls(engine)
    finally:
        await engine.dispose()


async def test_rol_runtime_restringido_pasa_el_guardarrail() -> None:
    """Con el DSN del rol runtime (NOSUPERUSER/NOBYPASSRLS), el guardarraíl pasa sin lanzar."""
    dsns = await provision_test_db()
    engine = create_async_engine(dsns["app_async"])
    try:
        await assert_runtime_role_cannot_bypass_rls(engine)  # no debe lanzar
    finally:
        await engine.dispose()


async def test_tabla_rls_sin_force_hace_fallar_el_arranque() -> None:
    """Una tabla con RLS habilitada pero sin FORCE aborta el arranque (defensa en profundidad).

    El owner de una tabla en `ENABLE` sin `FORCE` se salta su política RLS. Se degrada `companies`
    a ese estado (como superusuario), se comprueba que el guard falla contra el engine del rol
    runtime, y se restaura `FORCE` en `finally` por higiene de la BD efímera.
    """
    dsns = await provision_test_db()
    admin = await asyncpg.connect(dsns["admin"])
    engine = create_async_engine(dsns["app_async"])
    try:
        await admin.execute("ALTER TABLE companies NO FORCE ROW LEVEL SECURITY")
        with pytest.raises(RlsEnabledWithoutForceError):
            await assert_runtime_role_cannot_bypass_rls(engine)
    finally:
        await admin.execute("ALTER TABLE companies FORCE ROW LEVEL SECURITY")
        await admin.close()
        await engine.dispose()
