"""Fixtures para pruebas contra MySQL real.

Usan VALKERY_TEST_DB_URL (variable de entorno o .env). Si no está definida,
estas pruebas se saltan. Por seguridad, el nombre de la base DEBE terminar en
"_test": el esquema se destruye y se recrea con Alembic en cada ejecución.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from valkery_core.config import ENV_FILE, REPO_ROOT
from valkery_core.db import create_engine, create_session_factory
from valkery_core.models import Base, Device

from ..conftest import TEST_IMEI

ALEMBIC_INI = REPO_ROOT / "database" / "alembic.ini"


def _test_db_url() -> str | None:
    return os.environ.get("VALKERY_TEST_DB_URL") or dotenv_values(ENV_FILE).get("VALKERY_TEST_DB_URL")


def alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    os.environ["VALKERY_MIGRATION_DB_URL"] = url
    return cfg


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = _test_db_url()
    if not url:
        pytest.skip("VALKERY_TEST_DB_URL no configurada: se omiten pruebas de MySQL")
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.exit(f"VALKERY_TEST_DB_URL debe apuntar a una base *_test (es '{database}')", returncode=2)
    return url


@pytest.fixture(scope="session")
def migrated_db(test_db_url: str) -> str:
    """Esquema limpio: downgrade total + upgrade head (prueba ambas direcciones)."""
    cfg = alembic_config(test_db_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return test_db_url


@pytest.fixture
async def session_factory(migrated_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(migrated_db)
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


@pytest.fixture
async def device(session_factory: async_sessionmaker[AsyncSession]) -> Device:
    async with session_factory.begin() as db:
        dev = Device(imei=TEST_IMEI, name="Simulador", enabled=True)
        db.add(dev)
        await db.flush()
    return dev


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT
