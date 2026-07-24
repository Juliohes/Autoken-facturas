"""Utilidades de test contra un PostgreSQL real (esquema de tenancy + rol runtime).

No es un módulo de tests (prefijo `_`): provee el arranque común para las suites que necesitan la
BD real (RLS, resolución de subdominio, etc.): crea una BD efímera, corre las migraciones como
superusuario y da los DSN de admin (salta RLS, para sembrar) y del rol runtime `autoken_app`.
"""

from __future__ import annotations

import asyncio
import os
import sys
from uuid import uuid4

import asyncpg

ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432"
)


def _worker_suffix() -> str:
    """Sufijo único por worker para aislar la BD efímera en ejecución paralela (#56).

    Bajo `pytest-xdist` cada worker exporta `PYTEST_XDIST_WORKER` (gw0, gw1...): se usa tal cual.
    Sin xdist (ejecución en un solo proceso) no hay colisión posible entre procesos, pero se
    ancla igualmente al PID para que dos ejecuciones simultáneas de la suite en la misma máquina
    no compartan la BD `autoken_test`. Así la suite corre en paralelo sin el flake y se puede
    retirar el `-p no:randomly`.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    return worker if worker else f"p{os.getpid()}"


# Nombre de la BD efímera de test, único por worker (#56): evita que dos workers dropeen/creen la
# misma base a la vez. Los identificadores de BD de Postgres van sin comillas aquí porque el sufijo
# es alfanumérico controlado (worker id o PID), no entrada externa.
TEST_DB = f"autoken_test_{_worker_suffix()}"
APP_PASSWORD = "apptest"  # noqa: S105  (solo para la BD efímera de test)


async def _run_migrations(db_dsn: str) -> None:
    async_url = db_dsn.replace("postgresql://", "postgresql+asyncpg://")
    env = {**os.environ, "DATABASE_URL": async_url}
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


async def provision_test_db() -> dict[str, str]:
    """Crea la BD de test limpia, corre las migraciones y devuelve los DSN de admin y runtime."""
    root = await asyncpg.connect(f"{ADMIN_DSN}/postgres")
    try:
        await root.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{TEST_DB}' AND pid <> pg_backend_pid()"
        )
        await root.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
        await root.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await root.close()

    admin_dsn = f"{ADMIN_DSN}/{TEST_DB}"
    await _run_migrations(admin_dsn)

    root = await asyncpg.connect(admin_dsn)
    try:
        await root.execute(f"ALTER ROLE autoken_app WITH LOGIN PASSWORD '{APP_PASSWORD}'")
    finally:
        await root.close()

    host = ADMIN_DSN.split("@", 1)[1]
    return {
        "admin": admin_dsn,
        "app": f"postgresql://autoken_app:{APP_PASSWORD}@{host}/{TEST_DB}",
        "app_async": f"postgresql+asyncpg://autoken_app:{APP_PASSWORD}@{host}/{TEST_DB}",
    }


async def seed_tenant(
    admin_dsn: str,
    slug: str,
    name: str,
    status: str = "active",
    *,
    custom_domain: str | None = None,
    is_demo: bool = False,
) -> str:
    """Inserta un tenant (como superusuario, saltando RLS) y devuelve su id."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        tenant_id = str(uuid4())
        await conn.execute(
            "INSERT INTO tenants (id, slug, name, status, custom_domain, is_demo) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            tenant_id,
            slug,
            name,
            status,
            custom_domain,
            is_demo,
        )
        return tenant_id
    finally:
        await conn.close()


async def seed_branding(
    admin_dsn: str,
    *,
    tenant_id: str,
    logo_url: str | None = None,
    color_primary: str | None = None,
    color_secondary: str | None = None,
    app_name: str | None = None,
    favicon: str | None = None,
) -> None:
    """Inserta la fila de `tenant_branding` de un tenant (como superusuario, saltando RLS, S4.2)."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(
            "INSERT INTO tenant_branding "
            "(tenant_id, logo_url, color_primary, color_secondary, app_name, favicon) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            tenant_id,
            logo_url,
            color_primary,
            color_secondary,
            app_name,
            favicon,
        )
    finally:
        await conn.close()


async def seed_user(
    admin_dsn: str,
    *,
    tenant_id: str | None,
    email: str,
    role: str = "user",
    status: str = "active",
    password_hash: str | None = None,
    totp_secret: str | None = None,
) -> str:
    """Inserta un usuario (como superusuario, saltando RLS) y devuelve su id.

    `tenant_id=None` corresponde a un `platform_admin` (no pertenece a ninguna asesoría, S1.3): en
    el esquema definitivo `users.tenant_id` es nullable; hasta que exista esa migración, sembrar
    un platform_admin fallará (parte del rojo del flujo de plataforma).
    """
    conn = await asyncpg.connect(admin_dsn)
    try:
        user_id = str(uuid4())
        await conn.execute(
            "INSERT INTO users (id, tenant_id, email, role, status, password_hash, totp_secret) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            user_id,
            tenant_id,
            email,
            role,
            status,
            password_hash,
            totp_secret,
        )
        return user_id
    finally:
        await conn.close()


async def suspend_tenant(admin_dsn: str, tenant_id: str) -> None:
    """Marca un tenant como suspendido (superusuario). Su subdominio deja de resolver (S1.2)."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute("UPDATE tenants SET status = 'suspended' WHERE id = $1", tenant_id)
    finally:
        await conn.close()


async def seed_company(
    admin_dsn: str,
    *,
    tenant_id: str,
    name: str,
    cif: str,
    status: str = "active",
    notes: str | None = None,
) -> str:
    """Inserta una empresa del tenant (como superusuario, saltando RLS) y devuelve su id."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        company_id = str(uuid4())
        await conn.execute(
            "INSERT INTO companies (id, tenant_id, name, cif, status, notes) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            company_id,
            tenant_id,
            name,
            cif,
            status,
            notes,
        )
        return company_id
    finally:
        await conn.close()


async def seed_membership(admin_dsn: str, *, user_id: str, company_id: str, tenant_id: str) -> None:
    """Vincula un usuario a una empresa (membership), como superusuario (saltando RLS)."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(
            "INSERT INTO memberships (user_id, company_id, tenant_id) VALUES ($1, $2, $3)",
            user_id,
            company_id,
            tenant_id,
        )
    finally:
        await conn.close()
