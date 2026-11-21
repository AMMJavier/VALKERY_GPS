"""Autenticación, sesión y gestión de usuarios."""

from __future__ import annotations

from conftest import PASSWORD
from sqlalchemy import select

from valkery_core.models import AuditLog

API = "/api/v1"


async def test_login_and_me(client, make_user):
    _, headers = await make_user("ana", ("viewer",))
    response = await client.get(f"{API}/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "ana" and body["roles"] == ["viewer"]
    assert "positions:read" in body["permissions"] and "users:manage" not in body["permissions"]
    assert "password_hash" not in body


async def test_wrong_password_and_unknown_user_same_answer(client, make_user):
    await make_user("ana", ("viewer",))
    bad = await client.post(f"{API}/auth/login", json={"username": "ana", "password": "incorrecta"})
    unknown = await client.post(f"{API}/auth/login", json={"username": "nadie", "password": "incorrecta"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()


async def test_lockout_after_failed_attempts(client, make_user):
    await make_user("ana", ("viewer",))
    for _ in range(3):
        assert (await client.post(f"{API}/auth/login", json={"username": "ana", "password": "mal"})).status_code == 401
    locked = await client.post(f"{API}/auth/login", json={"username": "ana", "password": PASSWORD})
    assert locked.status_code == 429


async def test_requests_without_or_with_bad_token(client):
    assert (await client.get(f"{API}/devices")).status_code == 401
    bad = await client.get(f"{API}/devices", headers={"Authorization": "Bearer xxx.yyy.zzz"})
    assert bad.status_code == 401


async def test_change_password_revokes_old_tokens(client, make_user):
    _, headers = await make_user("ana", ("viewer",))
    response = await client.post(
        f"{API}/auth/change-password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "otra-clave-segura-456"},
    )
    assert response.status_code == 204
    assert (await client.get(f"{API}/auth/me", headers=headers)).status_code == 401
    relogin = await client.post(f"{API}/auth/login", json={"username": "ana", "password": "otra-clave-segura-456"})
    assert relogin.status_code == 200


async def test_admin_manages_users_and_changes_take_effect(client, make_user, session_factory):
    _, admin = await make_user("admin", ("admin",))
    created = await client.post(
        f"{API}/users",
        headers=admin,
        json={"username": "operador", "password": "clave-operador-1", "roles": ["operator"], "full_name": "Op"},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert created.json()["roles"] == ["operator"]

    dup = await client.post(
        f"{API}/users", headers=admin, json={"username": "operador", "password": "clave-operador-1", "roles": ["viewer"]}
    )
    assert dup.status_code == 409

    login = await client.post(f"{API}/auth/login", json={"username": "operador", "password": "clave-operador-1"})
    op_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get(f"{API}/auth/me", headers=op_headers)).status_code == 200

    disabled = await client.patch(f"{API}/users/{user_id}", headers=admin, json={"enabled": False})
    assert disabled.status_code == 200 and disabled.json()["enabled"] is False
    # Deshabilitar invalida la sesión abierta y bloquea el login.
    assert (await client.get(f"{API}/auth/me", headers=op_headers)).status_code == 401
    assert (
        await client.post(f"{API}/auth/login", json={"username": "operador", "password": "clave-operador-1"})
    ).status_code == 401

    async with session_factory() as db:
        actions = (await db.scalars(select(AuditLog.action).order_by(AuditLog.id))).all()
    assert {"login", "user_created", "user_updated", "login_failed"} <= set(actions)


async def test_user_validation(client, make_user):
    _, admin = await make_user()
    short = await client.post(f"{API}/users", headers=admin, json={"username": "x1", "password": "corta", "roles": []})
    assert short.status_code == 422
    bad_role = await client.post(
        f"{API}/users", headers=admin, json={"username": "pepe", "password": "clave-larga-123", "roles": ["superuser"]}
    )
    assert bad_role.status_code == 422


async def test_cannot_remove_last_admin(client, make_user):
    admin_user, admin = await make_user()
    response = await client.patch(f"{API}/users/{admin_user.id}", headers=admin, json={"roles": ["viewer"]})
    assert response.status_code == 409


async def test_roles_listing(client, make_user):
    _, admin = await make_user()
    roles = {r["name"]: r for r in (await client.get(f"{API}/users/roles", headers=admin)).json()}
    assert set(roles) == {"admin", "operator", "viewer"}
    assert "commands:immobilize" not in roles["admin"]["permissions"]
