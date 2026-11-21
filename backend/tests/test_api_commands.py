"""API de comandos: permisos, doble confirmación, precondiciones y auditoría."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from conftest import PASSWORD
from sqlalchemy import delete, select, update

from valkery_api.main import create_app
from valkery_core.config import CoreSettings
from valkery_core.models import AuditLog, Command, DeviceState, Role, RolePermission

API = "/api/v1"


def core(**overrides) -> CoreSettings:
    values = {"commands_enabled": True, "commands_relay_enabled": True}
    values.update(overrides)
    return CoreSettings(_env_file=None, **values)


@pytest.fixture
async def immobilizer_role(session_factory):
    """Rol de prueba con inmovilización. roles no se vacía entre pruebas (datos sembrados): se borra al final."""
    async with session_factory.begin() as db:
        await db.execute(delete(Role).where(Role.name == "inmovilizador"))
        role = Role(name="inmovilizador", description="pruebas")
        db.add(role)
        await db.flush()
        db.add_all(RolePermission(role_id=role.id, permission=p) for p in ("commands:send", "commands:immobilize"))
    yield
    async with session_factory.begin() as db:
        await db.execute(delete(Role).where(Role.name == "inmovilizador"))


@pytest.fixture
async def parked(session_factory, device):
    now = datetime.now(UTC)
    async with session_factory.begin() as db:
        db.add(
            DeviceState(
                device_id=device.id,
                online=True,
                last_seen=now - timedelta(seconds=5),
                last_gps_time=now - timedelta(seconds=10),
                ignition=False,
                speed=0,
                movement=False,
                dout1=False,
            )
        )
    return device


def client_with(session_factory, settings, core_settings):
    app = create_app(settings, session_factory=session_factory, core_settings=core_settings)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def cmd_client(session_factory, settings):
    async with client_with(session_factory, settings, core()) as c:
        yield c


async def login(client, username):
    r = await client.post(f"{API}/auth/login", json={"username": username, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def operator(make_user, immobilizer_role, cmd_client):
    await make_user("piloto", ("viewer", "inmovilizador"))
    return await login(cmd_client, "piloto")


async def test_types_reflect_permissions_and_switches(cmd_client, make_user, session_factory, settings):
    _, viewer = await make_user("ver", ("viewer",))
    assert (await cmd_client.get(f"{API}/commands/types", headers=viewer)).status_code == 403

    await make_user("admin", ("admin",))
    admin = await login(cmd_client, "admin")
    types = {t["command_type"]: t for t in (await cmd_client.get(f"{API}/commands/types", headers=admin)).json()}
    assert types["GET_VERSION"]["allowed"] is True
    assert types["RELEASE"]["allowed"] is True
    assert types["IMMOBILIZE"]["allowed"] is False and "commands:immobilize" in types["IMMOBILIZE"]["unavailable_reason"]

    async with client_with(session_factory, settings, core(commands_relay_enabled=False)) as off:
        types = {t["command_type"]: t for t in (await off.get(f"{API}/commands/types", headers=admin)).json()}
    assert types["GET_VERSION"]["allowed"] is True
    assert types["RELEASE"]["allowed"] is False and "prueba física" in types["RELEASE"]["unavailable_reason"]


async def test_diagnostic_is_authorized_immediately(cmd_client, make_user, parked):
    await make_user("admin", ("admin",))
    admin = await login(cmd_client, "admin")
    r = await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=admin, json={"command_type": "GET_VERSION"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "AUTORIZADO" and body["command_text"] == "getver" and body["confirmed_by"] is not None


async def test_admin_cannot_immobilize_without_explicit_permission(cmd_client, make_user, parked):
    await make_user("admin", ("admin",))
    admin = await login(cmd_client, "admin")
    r = await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=admin, json={"command_type": "IMMOBILIZE"})
    assert r.status_code == 403


async def test_immobilize_double_confirmation_flow(cmd_client, operator, parked, session_factory):
    r = await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "IMMOBILIZE"})
    assert r.status_code == 201, r.text
    cmd = r.json()
    assert cmd["status"] == "CREADO" and cmd["expected_dout1"] is True and cmd["confirmed_by"] is None
    url = f"{API}/commands/{cmd['id']}"

    no_ack = await cmd_client.post(f"{url}/confirm", headers=operator, json={"password": PASSWORD, "acknowledge_safety": False})
    assert no_ack.status_code == 422
    wrong = await cmd_client.post(f"{url}/confirm", headers=operator, json={"password": "mala", "acknowledge_safety": True})
    assert wrong.status_code == 403
    assert (await cmd_client.get(url, headers=operator)).json()["status"] == "CREADO"

    ok = await cmd_client.post(f"{url}/confirm", headers=operator, json={"password": PASSWORD, "acknowledge_safety": True})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["status"] == "AUTORIZADO" and body["confirmed_at"]
    assert {c["stage"] for c in body["preconditions"]} == {"request", "confirm"}
    assert all(c["ok"] for c in body["preconditions"])

    again = await cmd_client.post(f"{url}/confirm", headers=operator, json={"password": PASSWORD, "acknowledge_safety": True})
    assert again.status_code == 409

    async with session_factory() as db:
        actions = (await db.scalars(select(AuditLog.action).order_by(AuditLog.id))).all()
    assert ["command_requested", "command_confirm_failed", "command_confirmed"] == [
        a for a in actions if a.startswith("command_")
    ]


async def test_unsafe_state_is_blocked_with_checks(cmd_client, operator, parked, session_factory):
    async with session_factory.begin() as db:
        await db.execute(update(DeviceState).values(ignition=True, speed=25, movement=True))
    r = await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "IMMOBILIZE"})
    assert r.status_code == 409
    failed = {c["name"] for c in r.json()["detail"]["checks"] if not c["ok"]}
    assert {"ignition_off", "speed_zero", "not_moving"} <= failed
    async with session_factory() as db:
        assert await db.scalar(select(Command)) is None
        assert "command_blocked" in (await db.scalars(select(AuditLog.action))).all()


async def test_offline_device_is_blocked(cmd_client, operator, parked, session_factory):
    async with session_factory.begin() as db:
        await db.execute(update(DeviceState).values(online=False))
    r = await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "GET_STATUS"})
    assert r.status_code == 409 and "conectado" in r.json()["detail"]["message"]


async def test_state_change_before_confirm_rejects(cmd_client, operator, parked, session_factory):
    cmd = (await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "IMMOBILIZE"})).json()
    async with session_factory.begin() as db:
        await db.execute(update(DeviceState).values(ignition=True))
    r = await cmd_client.post(f"{API}/commands/{cmd['id']}/confirm", headers=operator, json={"password": PASSWORD, "acknowledge_safety": True})
    assert r.status_code == 409
    assert (await cmd_client.get(f"{API}/commands/{cmd['id']}", headers=operator)).json()["status"] == "RECHAZADO"


async def test_one_active_command_per_device(cmd_client, operator, parked):
    first = await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "IMMOBILIZE"})
    second = await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "GET_VERSION"})
    assert first.status_code == 201 and second.status_code == 409


async def test_expired_confirmation(cmd_client, operator, parked, session_factory):
    cmd = (await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "IMMOBILIZE"})).json()
    async with session_factory.begin() as db:
        await db.execute(update(Command).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    r = await cmd_client.post(f"{API}/commands/{cmd['id']}/confirm", headers=operator, json={"password": PASSWORD, "acknowledge_safety": True})
    assert r.status_code == 409
    assert (await cmd_client.get(f"{API}/commands/{cmd['id']}", headers=operator)).json()["status"] == "EXPIRADO"


async def test_only_requester_can_confirm_and_cancel(cmd_client, operator, make_user, parked, immobilizer_role):
    await make_user("otro", ("viewer", "inmovilizador"))
    other = await login(cmd_client, "otro")
    cmd = (await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "IMMOBILIZE"})).json()
    r = await cmd_client.post(f"{API}/commands/{cmd['id']}/confirm", headers=other, json={"password": PASSWORD, "acknowledge_safety": True})
    assert r.status_code == 403

    cancelled = await cmd_client.post(f"{API}/commands/{cmd['id']}/cancel", headers=operator)
    assert cancelled.json()["status"] == "RECHAZADO" and cancelled.json()["failure_reason"] == "cancelado por el usuario"
    assert (await cmd_client.post(f"{API}/commands/{cmd['id']}/cancel", headers=operator)).status_code == 409
    # Tras cancelar, el equipo queda libre para otro comando.
    assert (await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "GET_INFO"})).status_code == 201


async def test_commands_disabled_by_default_configuration(session_factory, settings, make_user, parked):
    async with client_with(session_factory, settings, CoreSettings(_env_file=None)) as c:
        await make_user("admin", ("admin",))
        admin = await login(c, "admin")
        r = await c.post(f"{API}/devices/{parked.id}/commands", headers=admin, json={"command_type": "GET_VERSION"})
    assert r.status_code == 403 and "VALKERY_COMMANDS_ENABLED" in r.json()["detail"]


async def test_unknown_type_and_listing(cmd_client, operator, parked):
    bad = await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "setdigout 1"})
    assert bad.status_code == 422  # no hay comandos arbitrarios
    await cmd_client.post(f"{API}/devices/{parked.id}/commands", headers=operator, json={"command_type": "GET_VERSION"})
    listing = (await cmd_client.get(f"{API}/devices/{parked.id}/commands", headers=operator)).json()
    assert [c["command_type"] for c in listing] == ["GET_VERSION"]
