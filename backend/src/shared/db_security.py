"""Guardarraíl de arranque: el rol runtime de la app NO debe poder saltarse la RLS (ADR-0014).

El aislamiento multi-tenant (ADR-0001) descansa por completo en un supuesto: la app se conecta a
Postgres como un rol runtime restringido (NOSUPERUSER, NOBYPASSRLS, no-owner de las tablas), de modo
que las políticas RLS le aplican. Si por un error de despliegue (un `DATABASE_URL` con el
superusuario, o un rol al que se le concedió BYPASSRLS) la app se conectara con privilegios
elevados, la RLS se saltaría en silencio y una asesoría vería los datos de otra: el fallo de
seguridad más grave posible en esta plataforma, e invisible en funcionamiento normal.

Este módulo comprueba ese invariante contra la conexión REAL de la app y **hace fallar el arranque**
(fail-loud, regla de oro 8) si no se cumple, en vez de levantar la app con el aislamiento roto. Es
un chequeo de arranque de coste despreciable (una consulta a `pg_roles`), no de cada petición.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Interroga los privilegios del rol con el que la conexión está autenticada (`current_user`), no un
# nombre fijo: así el guard es correcto sea cual sea el rol configurado en `DATABASE_URL`.
_ROLE_PRIVILEGES_QUERY = text(
    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
)

# Cuenta las tablas con RLS habilitada (`relrowsecurity`) pero SIN forzar (`relforcerowsecurity`).
# Postgres deja que el OWNER de una tabla se salte una política RLS que solo esté en `ENABLE`; solo
# `FORCE ROW LEVEL SECURITY` obliga también al owner. Una sola tabla en ese estado anularía el
# aislamiento para su propietario, así que el invariante es: toda tabla con RLS debe estar en FORCE.
# Se excluyen los esquemas del sistema, cuyas tablas no son de negocio.
_RLS_WITHOUT_FORCE_QUERY = text(
    "SELECT count(*) AS n FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE c.relrowsecurity AND NOT c.relforcerowsecurity "
    "AND n.nspname NOT IN ('pg_catalog', 'information_schema')"
)


class RuntimeRoleCanBypassRlsError(RuntimeError):
    """El rol con el que la app se conecta puede saltarse la RLS: se aborta el arranque."""


class RlsEnabledWithoutForceError(RuntimeError):
    """Hay tablas con RLS habilitada pero sin FORCE: su owner la eludiría. Se aborta el arranque."""


async def assert_runtime_role_cannot_bypass_rls(engine: AsyncEngine) -> None:
    """Falla si el rol de conexión de `engine` puede eludir la RLS por privilegio o por ownership.

    Comprueba dos invariantes contra la conexión REAL de la app y aborta el arranque (fail-loud) si
    alguno se rompe:

    1. El rol `current_user` no es superusuario ni tiene `BYPASSRLS`
       (`RuntimeRoleCanBypassRlsError`). Ante la duda (sin fila en `pg_roles`), fail-closed.
    2. No existe ninguna tabla con RLS habilitada pero sin `FORCE ROW LEVEL SECURITY`
       (`RlsEnabledWithoutForceError`): el owner de una tabla así se saltaría la política. Es
       defensa en profundidad frente a una migración futura que haga `ENABLE` y olvide `FORCE`.
    """
    async with engine.connect() as conn:
        row = (await conn.execute(_ROLE_PRIVILEGES_QUERY)).first()
        rls_without_force = (await conn.execute(_RLS_WITHOUT_FORCE_QUERY)).scalar_one()
    if row is None:
        raise RuntimeRoleCanBypassRlsError(
            "No se pudieron determinar los privilegios del rol de conexión (current_user sin fila "
            "en pg_roles). Se aborta el arranque por seguridad (ADR-0014)."
        )
    if row.rolsuper or row.rolbypassrls:
        raise RuntimeRoleCanBypassRlsError(
            "El rol con el que la app se conecta a Postgres puede saltarse la RLS "
            f"(rolsuper={row.rolsuper}, rolbypassrls={row.rolbypassrls}). El aislamiento "
            "multi-tenant quedaría anulado. La app debe conectarse con el rol runtime restringido "
            "(NOSUPERUSER, NOBYPASSRLS, no-owner); revisa DATABASE_URL. Arranque abortado "
            "(ADR-0014)."
        )
    if rls_without_force > 0:
        raise RlsEnabledWithoutForceError(
            f"Hay {rls_without_force} tabla(s) con RLS habilitada pero sin FORCE ROW LEVEL "
            "SECURITY. El owner de una tabla en ese estado se salta la política RLS, anulando el "
            "aislamiento multi-tenant para su propietario. Toda tabla de negocio con RLS debe usar "
            "FORCE; revisa las migraciones. Arranque abortado (ADR-0014)."
        )
