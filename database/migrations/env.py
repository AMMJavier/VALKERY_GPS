"""Entorno Alembic: importa valkery_core.models y usa VALKERY_DB_URL (desde .env).

Uso (desde la raíz del repo):
    alembic -c database/alembic.ini upgrade head
    alembic -c database/alembic.ini check        # ¿modelos y BD coinciden?

Referencia Traccar: schema/changelog-*.xml (Liquibase)
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from valkery_core.config import get_core_settings
from valkery_core.db.session import create_engine
from valkery_core.models import Base

config = context.config
# Las pruebas ejecutan Alembic desde código y no quieren que se reconfigure el logging.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _db_url() -> str:
    # VALKERY_MIGRATION_DB_URL permite migrar otra base (p. ej. la de pruebas).
    return os.environ.get("VALKERY_MIGRATION_DB_URL") or get_core_settings().db_url


def run_migrations_offline() -> None:
    """Genera SQL sin conectarse: alembic ... upgrade head --sql"""
    context.configure(
        url=_db_url().replace("+aiomysql", "+pymysql"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(_db_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
