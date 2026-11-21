"""Fixtures de la API contra MySQL (base *_test, ver valkery_core.testing).

Esta carpeta NO es un paquete (sin __init__.py) para no chocar con
gps-server/tests; por eso los archivos usan el prefijo test_api_.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from valkery_api.core.config import ApiSettings
from valkery_api.main import create_app
from valkery_api.services.users import create_user
from valkery_core.db import create_engine, create_session_factory
from valkery_core.models import Device, User
from valkery_core.testing import check_test_database, get_test_db_url, migrate_clean, truncate_all

PASSWORD = "clave-de-prueba-123"
TEST_IMEI = "356307042441013"


def api_settings(**overrides) -> ApiSettings:
    values = {
        "jwt_secret": "secreto-de-pruebas-" + "x" * 32,
        "jwt_expire_min": 60,
        "login_max_attempts": 3,
        "login_lockout_min": 15,
        "ws_poll_s": 0.1,
        "page_max": 1000,
    }
    values.update(overrides)
    return ApiSettings(_env_file=None, **values)


@pytest.fixture(scope="session")
def db_url() -> str:
    url = get_test_db_url()
    if not url:
        pytest.skip("VALKERY_TEST_DB_URL no configurada: se omiten pruebas de la API")
    try:
        check_test_database(url)
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=2)
    migrate_clean(url)
    return url


@pytest.fixture
async def session_factory(db_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(db_url)
    await truncate_all(engine)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


@pytest.fixture
def settings() -> ApiSettings:
    return api_settings()


@pytest.fixture
async def client(session_factory, settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, session_factory=session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


MakeUser = Callable[..., Awaitable[tuple[User, dict[str, str]]]]


@pytest.fixture
def make_user(session_factory, client) -> MakeUser:
    """Crea un usuario con roles y devuelve (usuario, cabeceras Authorization)."""

    async def factory(username: str = "admin", roles: tuple[str, ...] = ("admin",)) -> tuple[User, dict[str, str]]:
        async with session_factory.begin() as db:
            user = await create_user(db, username=username, password=PASSWORD, roles=list(roles))
        response = await client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return user, {"Authorization": f"Bearer {response.json()['access_token']}"}

    return factory


@pytest.fixture
async def device(session_factory) -> Device:
    async with session_factory.begin() as db:
        dev = Device(imei=TEST_IMEI, name="Simulador", enabled=True)
        db.add(dev)
        await db.flush()
    return dev
