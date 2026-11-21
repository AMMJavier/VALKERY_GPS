"""Utilidades para pruebas contra MySQL (compartidas por gps-server y backend).

La base de pruebas se toma de VALKERY_TEST_DB_URL (entorno o .env) y DEBE
llamarse *_test: el esquema se destruye y se recrea en cada ejecución.
"""

from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import ENV_FILE, REPO_ROOT
from .models import Base

ALEMBIC_INI = REPO_ROOT / "database" / "alembic.ini"

# Tablas con datos sembrados por las migraciones: no se vacían entre pruebas.
SEED_TABLES = frozenset({"roles", "role_permissions"})

_migrated: set[str] = set()


def get_test_db_url() -> str | None:
    return os.environ.get("VALKERY_TEST_DB_URL") or dotenv_values(ENV_FILE).get("VALKERY_TEST_DB_URL")


def check_test_database(url: str) -> None:
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        raise RuntimeError(f"VALKERY_TEST_DB_URL debe apuntar a una base *_test (es '{database}')")


def alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    os.environ["VALKERY_MIGRATION_DB_URL"] = url
    return cfg


def migrate_clean(url: str) -> None:
    """downgrade base + upgrade head, una vez por proceso de pytest."""
    check_test_database(url)
    if url in _migrated:
        return
    cfg = alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    _migrated.add(url)


async def truncate_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in SEED_TABLES:
                await conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
