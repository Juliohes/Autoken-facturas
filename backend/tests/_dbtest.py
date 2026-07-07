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
TEST_DB = "autoken_test"
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


async def seed_tenant(admin_dsn: str, slug: str, name: str, status: str = "active") -> str:
    """Inserta un tenant (como superusuario, saltando RLS) y devuelve su id."""
    conn = await asyncpg.connect(admin_dsn)
    try:
        tenant_id = str(uuid4())
        await conn.execute(
            "INSERT INTO tenants (id, slug, name, status) VALUES ($1, $2, $3, $4)",
            tenant_id,
            slug,
            name,
            status,
        )
        return tenant_id
    finally:
        await conn.close()
