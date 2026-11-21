"""Fixtures para pruebas contra MySQL real.

Usan VALKERY_TEST_DB_URL (variable de entorno o .env). Si no está definida,
estas pruebas se saltan. Por seguridad, el nombre de la base DEBE terminar en
"_test": el esquema se destruye y se recrea con Alembic en cada ejecución.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from valkery_core.db import create_engine, create_session_factory
from valkery_core.models import Device
from valkery_core.testing import alembic_config, check_test_database, migrate_clean, get_test_db_url, truncate_all

from ..conftest import TEST_IMEI

__all__ = ["alembic_config"]


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """Esquema limpio: downgrade total + upgrade head (prueba ambas direcciones)."""
    url = get_test_db_url()
    if not url:
        pytest.skip("VALKERY_TEST_DB_URL no configurada: se omiten pruebas de MySQL")
    try:
        check_test_database(url)
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=2)
    migrate_clean(url)
    return url


@pytest.fixture
async def session_factory(migrated_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(migrated_db)
    await truncate_all(engine)
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
