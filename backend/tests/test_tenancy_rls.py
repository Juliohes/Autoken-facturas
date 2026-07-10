"""Tests de comportamiento de S1.1: aislamiento multi-tenant por RLS (spec docs/specs/S1.1).

Se ejecutan contra un **PostgreSQL real** (la RLS no existe en SQLite). Un fixture crea una BD de
test, corre las migraciones reales (como superusuario) y expone dos conexiones:
- `admin`: superusuario, **salta** la RLS -> se usa solo para SEMBRAR datos de varios tenants.
- `app`: el rol runtime `autoken_app` (NOSUPERUSER, NOBYPASSRLS, no-owner) -> la RLS le aplica;
  con él se comprueba la visibilidad fijando `app.tenant_id` / `app.company_id`.

Requiere un Postgres accesible en `TEST_DATABASE_ADMIN_DSN` (por defecto, docker en localhost).
Cada test = un escenario Given/When/Then de la spec (C1..C9).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import asyncpg
import pytest

from tests._dbtest import TEST_DB as _TEST_DB  # nombre único por worker (#56)

_ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432"
)
_APP_PASSWORD = "apptest"  # noqa: S105  (solo para la BD efímera de test)

# Nombres reales del Excel de empresas (entregas/Empresas_CIF_NIF.xlsx) para C9.
_CIF_SOCIEDAD = ("3L INTERNACIONAL", "A39031620")
_NIF_AUTONOMO = ("ALBERTO CAÑA REGALADO", "76072394D")


async def _run_migrations(db_dsn: str) -> None:
    """Corre `alembic upgrade head` contra la BD de test usando el DSN async de la app."""
    import asyncio
    import sys

    async_url = db_dsn.replace("postgresql://", "postgresql+asyncpg://")
    env = {**os.environ, "DATABASE_URL": async_url}
    # `python -m alembic` en vez de una ruta fija a `.venv/bin`: funciona en local y en CI.
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        "head",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"alembic upgrade head falló:\n{out.decode()}")


@pytest.fixture
async def db() -> AsyncIterator[dict[str, str]]:
    """BD de test limpia + migraciones aplicadas; devuelve los DSN de admin y de la app."""
    root = await asyncpg.connect(f"{_ADMIN_DSN}/postgres")
    try:
        await root.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{_TEST_DB}' AND pid <> pg_backend_pid()"
        )
        await root.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB}"')
        await root.execute(f'CREATE DATABASE "{_TEST_DB}"')
    finally:
        await root.close()

    admin_dsn = f"{_ADMIN_DSN}/{_TEST_DB}"
    await _run_migrations(admin_dsn)

    # La migración crea el rol runtime sin login; la BD de test le pone una clave para conectarse.
    root = await asyncpg.connect(admin_dsn)
    try:
        await root.execute(f"ALTER ROLE autoken_app WITH LOGIN PASSWORD '{_APP_PASSWORD}'")
    finally:
        await root.close()

    host = _ADMIN_DSN.split("@", 1)[1]
    app_dsn = f"postgresql://autoken_app:{_APP_PASSWORD}@{host}/{_TEST_DB}"
    app_async = f"postgresql+asyncpg://autoken_app:{_APP_PASSWORD}@{host}/{_TEST_DB}"
    yield {"admin": admin_dsn, "app": app_dsn, "app_async": app_async}


async def _seed_company(admin_dsn: str, tenant_id: str, name: str, cif: str) -> str:
    """Inserta (como superusuario, saltando RLS) una company de un tenant. Devuelve su id."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(
            "INSERT INTO tenants (id, slug, name, status) VALUES ($1, $2, $3, 'active') "
            "ON CONFLICT (id) DO NOTHING",
            tenant_id,
            f"t-{tenant_id[:8]}",
            name,
        )
        company_id = str(uuid4())
        await conn.execute(
            "INSERT INTO companies (id, tenant_id, name, cif, status) "
            "VALUES ($1, $2, $3, $4, 'pending')",
            company_id,
            tenant_id,
            name,
            cif,
        )
        return company_id
    finally:
        await conn.close()


async def _companies_visible(app_dsn: str, tenant_id: str | None, company_id: str | None) -> int:
    """Cuenta las companies visibles para el rol runtime con el contexto de sesión dado."""
    conn = await asyncpg.connect(app_dsn)
    try:
        async with conn.transaction():
            if tenant_id is not None:
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            if company_id is not None:
                await conn.execute("SELECT set_config('app.company_id', $1, true)", company_id)
            return await conn.fetchval("SELECT count(*) FROM companies")
    finally:
        await conn.close()


# --- C1..C3: aislamiento por tenant -------------------------------------------------------------


async def test_c1_sin_tenant_id_no_se_ve_ninguna_fila(db: dict[str, str]) -> None:
    """C1: sin `app.tenant_id` fijado, el rol runtime no ve ninguna fila (el test estrella)."""
    await _seed_company(db["admin"], str(uuid4()), *_CIF_SOCIEDAD)
    await _seed_company(db["admin"], str(uuid4()), *_NIF_AUTONOMO)
    assert await _companies_visible(db["app"], tenant_id=None, company_id=None) == 0


async def test_c2_tenant_distinto_no_ve_filas_de_otro(db: dict[str, str]) -> None:
    """C2: con un `app.tenant_id` distinto al del dato, 0 filas."""
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)
    assert await _companies_visible(db["app"], tenant_id=tenant_b, company_id=None) == 0


async def test_c3_tenant_correcto_ve_solo_sus_filas(db: dict[str, str]) -> None:
    """C3: con el `app.tenant_id` correcto, se ven todas las filas de A y ninguna de B."""
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)
    await _seed_company(db["admin"], tenant_a, "OTRA SL", "B12345674")
    await _seed_company(db["admin"], tenant_b, *_NIF_AUTONOMO)
    assert await _companies_visible(db["app"], tenant_id=tenant_a, company_id=None) == 2


# --- C4: aislamiento por company ----------------------------------------------------------------


async def test_c4_contexto_company_solo_ve_su_empresa(db: dict[str, str]) -> None:
    """C4: con `app.company_id` fijado (contexto user), solo se ve esa empresa del tenant."""
    tenant_a = str(uuid4())
    company_x = await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)
    await _seed_company(db["admin"], tenant_a, *_NIF_AUTONOMO)  # company Y, no debe verse
    assert await _companies_visible(db["app"], tenant_id=tenant_a, company_id=company_x) == 1


# --- C5: escritura cruzada rechazada ------------------------------------------------------------


async def test_c5_escribir_en_otro_tenant_se_rechaza(db: dict[str, str]) -> None:
    """C5: con contexto tenant A, insertar una fila con tenant_id = B se rechaza (WITH CHECK)."""
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)  # crea el tenant A
    conn = await asyncpg.connect(db["app"])
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_a)
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "INSERT INTO companies (id, tenant_id, name, cif, status) "
                    "VALUES ($1, $2, 'INTRUSA', 'B12345674', 'pending')",
                    str(uuid4()),
                    tenant_b,
                )
    finally:
        await conn.close()


# --- C6: el rol runtime no puede saltarse la RLS ------------------------------------------------


async def test_c6_runtime_no_puede_desactivar_rls_ni_escalar_de_rol(db: dict[str, str]) -> None:
    """C6: el rol runtime no es dueño ni superusuario -> ni desactiva la RLS ni salta a otro rol."""
    conn = await asyncpg.connect(db["app"])
    try:
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("ALTER TABLE companies DISABLE ROW LEVEL SECURITY")
        # Tampoco puede escalar a un rol que sí saltaría la RLS.
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("SET ROLE postgres")
    finally:
        await conn.close()


# --- C7: audit_log append-only ------------------------------------------------------------------


async def test_c7_audit_log_es_append_only(db: dict[str, str]) -> None:
    """C7: el rol runtime hace INSERT en audit_log pero no UPDATE/DELETE (privilegios revocados)."""
    tenant_a = str(uuid4())
    await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)  # crea el tenant A
    conn = await asyncpg.connect(db["app"])
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_a)
            await conn.execute(
                "INSERT INTO audit_log (id, tenant_id, actor_id, action, entity, entity_id) "
                "VALUES ($1, $2, $3, 'created', 'company', $4)",
                str(uuid4()),
                tenant_a,
                str(uuid4()),
                str(uuid4()),
            )
        # Cada intento en su propio savepoint: si no, el 1er error aborta la transacción y el 2º
        # "pasaría" por transacción muerta, no por la revocación real (falso verde).
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_a)
                await conn.execute("UPDATE audit_log SET action = 'tampered'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_a)
                await conn.execute("DELETE FROM audit_log")
    finally:
        await conn.close()


# --- C8: guard anti-olvido de RLS ---------------------------------------------------------------


async def test_c8_toda_tabla_con_tenant_id_tiene_rls_forzada_y_politica(db: dict[str, str]) -> None:
    """C8: guard anti-olvido dinámico.

    Descubre en la BD toda tabla de negocio (la que tiene columna `tenant_id`, más `tenants`) y
    exige que TODAS tengan RLS habilitada + forzada y al menos una política. Así una tabla futura
    sin RLS rompe el test aunque nadie actualice una lista a mano.
    """
    conn = await asyncpg.connect(db["admin"])
    try:
        business = {
            r["table_name"]
            for r in await conn.fetch(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'tenant_id'"
            )
        } | {"tenants"}
        rows = await conn.fetch(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
            "  (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS n_policies "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = ANY($1::text[])",
            list(business),
        )
    finally:
        await conn.close()
    assert business >= {"tenants", "companies", "audit_log"}, f"pocas tablas: {business}"
    problemas = [
        r["relname"]
        for r in rows
        if not (r["relrowsecurity"] and r["relforcerowsecurity"] and r["n_policies"] >= 1)
    ]
    assert not problemas, f"tablas de negocio sin RLS forzada o sin política: {problemas}"


# --- C9: el esquema companies admite los CIF/NIF reales -----------------------------------------


async def test_c9_companies_admite_cif_de_sociedad_y_nif_de_autonomo(db: dict[str, str]) -> None:
    """C9: el esquema companies persiste tanto un CIF de sociedad como un NIF de autónomo."""
    tenant_a = str(uuid4())
    id_soc = await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)
    id_aut = await _seed_company(db["admin"], tenant_a, *_NIF_AUTONOMO)
    assert await _companies_visible(db["app"], tenant_id=tenant_a, company_id=None) == 2
    assert id_soc != id_aut


# --- Refuerzos de la auditoría de S1.1 ----------------------------------------------------------


async def _seed_user(admin_dsn: str, tenant_id: str) -> str:
    """Inserta un usuario del tenant (como superusuario). Devuelve su id."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        user_id = str(uuid4())
        await conn.execute(
            "INSERT INTO users (id, tenant_id, email, role) VALUES ($1, $2, $3, 'user')",
            user_id,
            tenant_id,
            f"u-{user_id[:8]}@example.com",
        )
        return user_id
    finally:
        await conn.close()


async def test_with_check_bloquea_escritura_en_otra_empresa_del_mismo_tenant(
    db: dict[str, str],
) -> None:
    """En contexto de empresa X, insertar una membership de la empresa Y (mismo tenant) se rechaza.

    Cubre el hueco que detectó la auditoría: el WITH CHECK debe incluir el nivel company, no solo
    el tenant. Sin el arreglo, esta escritura cruzaría la frontera de empresa.
    """
    tenant_a = str(uuid4())
    company_x = await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)
    company_y = await _seed_company(db["admin"], tenant_a, *_NIF_AUTONOMO)
    user_id = await _seed_user(db["admin"], tenant_a)
    conn = await asyncpg.connect(db["app"])
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_a)
            await conn.execute("SELECT set_config('app.company_id', $1, true)", company_x)
            # En su propia empresa, permitido.
            await conn.execute(
                "INSERT INTO memberships (user_id, company_id, tenant_id) VALUES ($1, $2, $3)",
                user_id,
                company_x,
                tenant_a,
            )
            # En otra empresa del mismo tenant, rechazado por el WITH CHECK de company.
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "INSERT INTO memberships (user_id, company_id, tenant_id) VALUES ($1, $2, $3)",
                    user_id,
                    company_y,
                    tenant_a,
                )
    finally:
        await conn.close()


async def test_runtime_no_puede_borrar_tenant_y_el_audit_log_sobrevive(db: dict[str, str]) -> None:
    """El rol runtime no tiene DELETE sobre tenants -> no puede vaciar el audit_log por cascada."""
    tenant_a = str(uuid4())
    await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)
    conn = await asyncpg.connect(db["app"])
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_a)
            await conn.execute(
                "INSERT INTO audit_log (id, tenant_id, actor_id, action, entity, entity_id) "
                "VALUES ($1, $2, $3, 'created', 'company', $4)",
                str(uuid4()),
                tenant_a,
                str(uuid4()),
                str(uuid4()),
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_a)
                await conn.execute("DELETE FROM tenants")
    finally:
        await conn.close()
    # La entrada de auditoría sigue ahí (contada como superusuario).
    admin = await asyncpg.connect(db["admin"])
    try:
        assert await admin.fetchval("SELECT count(*) FROM audit_log") == 1
    finally:
        await admin.close()


async def test_contexto_vacio_falla_cerrado_sin_reventar(db: dict[str, str]) -> None:
    """Un `app.company_id` vacío ('') se trata como sin contexto de empresa (NULLIF), no un 500."""
    tenant_a = str(uuid4())
    await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)
    await _seed_company(db["admin"], tenant_a, *_NIF_AUTONOMO)
    conn = await asyncpg.connect(db["app"])
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_a)
            await conn.execute("SELECT set_config('app.company_id', '', true)")  # vacío, no NULL
            # No revienta con 'invalid input syntax for uuid'; se comporta como asesoría (ve las 2).
            assert await conn.fetchval("SELECT count(*) FROM companies") == 2
    finally:
        await conn.close()


async def test_tenant_session_aisla_de_verdad_por_tenant_y_empresa(db: dict[str, str]) -> None:
    """El chokepoint real `tenant_session` (SET LOCAL) aísla como los tests de política (C3/C4)."""
    import os

    from shared import config
    from shared import db as db_module

    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    company_x = await _seed_company(db["admin"], tenant_a, *_CIF_SOCIEDAD)
    await _seed_company(db["admin"], tenant_a, *_NIF_AUTONOMO)  # company Y
    await _seed_company(db["admin"], tenant_b, "OTRO SL", "B12345674")

    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db["app_async"]
    config.get_settings.cache_clear()
    await db_module.dispose_engine()
    try:
        from sqlalchemy import text

        async with db_module.tenant_session(UUID(tenant_a)) as session:  # contexto asesoría
            assert await session.scalar(text("SELECT count(*) FROM companies")) == 2
        # Contexto de empresa X: solo ve X.
        async with db_module.tenant_session(UUID(tenant_a), UUID(company_x)) as session:
            assert await session.scalar(text("SELECT count(*) FROM companies")) == 1
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        config.get_settings.cache_clear()
        await db_module.dispose_engine()
