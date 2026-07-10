"""Entorno de migraciones Alembic (async).

La URL de la base de datos se toma de la configuración de la app
(`DATABASE_URL`), nunca de `alembic.ini`, para no versionar credenciales.
El `target_metadata` se conectará con los modelos SQLAlchemy en S1.1.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from shared.config import get_settings
from shared.db import Base

# Importa los modelos para que se registren en Base.metadata (autogenerate y target).
import tenancy.models  # noqa: F401  (efecto secundario: registrar tablas)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inyecta la URL real desde la configuración de la app (env var).
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Ejecuta migraciones en modo 'offline' (genera SQL sin conexión)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # `compare_type` y `compare_server_default` afinan la detección de deriva ORM<->migración que usa
    # el guard `alembic check` de CI (#49): sin ellos, un cambio de tipo o de server default en un
    # modelo sin su migración pasaría inadvertido. Verificado contra el head actual: no producen
    # falsos positivos (el esquema ORM y el migrado coinciden), así que el gate no es flaky.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Ejecuta migraciones en modo 'online' con engine async."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
