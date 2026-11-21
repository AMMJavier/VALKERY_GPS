"""Seguridad sin base de datos: tokens, contraseñas, bloqueo y roles iniciales."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import api_settings

from valkery_api.core.security import (
    InvalidToken,
    LoginGuard,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from valkery_core.config import REPO_ROOT
from valkery_core.enums import DEFAULT_ROLES, Permission


def test_password_hash_roundtrip():
    h = hash_password("una-clave-larga")
    assert h.startswith("$argon2")
    assert verify_password("una-clave-larga", h)
    assert not verify_password("otra", h)
    assert not verify_password("cualquiera", None)


def test_token_roundtrip_and_tampering():
    settings = api_settings()
    token, expires = create_access_token(7, 3, settings)
    user_id, version, exp = decode_access_token(token, settings)
    assert (user_id, version) == (7, 3) and abs((exp - expires).total_seconds()) < 1

    with pytest.raises(InvalidToken):
        decode_access_token(token, api_settings(jwt_secret="otro-secreto-" + "y" * 32))
    with pytest.raises(InvalidToken):
        decode_access_token(token[:-2] + "xx", settings)


def test_expired_and_wrong_type_tokens_rejected():
    settings = api_settings()
    past = datetime.now(UTC) - timedelta(hours=2)
    expired = jwt.encode(
        {"sub": "1", "ver": 0, "iat": past, "exp": past + timedelta(minutes=5), "typ": "access"},
        settings.jwt_secret,
    )
    with pytest.raises(InvalidToken):
        decode_access_token(expired, settings)
    other = jwt.encode(
        {"sub": "1", "ver": 0, "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5), "typ": "refresh"},
        settings.jwt_secret,
    )
    with pytest.raises(InvalidToken):
        decode_access_token(other, settings)


def test_placeholder_secret_rejected():
    with pytest.raises(ValueError):
        api_settings(jwt_secret="CAMBIAR" + "x" * 40)
    with pytest.raises(ValueError):
        api_settings(jwt_secret="corto")


def test_login_guard_locks_and_resets():
    guard = LoginGuard(max_attempts=3, lockout_s=60)
    for _ in range(3):
        assert not guard.is_locked("ana")
        guard.failure("ana")
    assert guard.is_locked("ana")
    assert not guard.is_locked("otro")
    guard.success("ana")
    assert not guard.is_locked("ana")


def test_migration_roles_match_enums():
    path = REPO_ROOT / "database" / "migrations" / "versions" / "0003_fase4_usuarios_auditoria.py"
    spec = importlib.util.spec_from_file_location("m0003", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert {name: set(perms) for name, (_, perms) in module.ROLES.items()} == {
        name: {p.value for p in perms} for name, (_, perms) in DEFAULT_ROLES.items()
    }
    # Nadie recibe inmovilización por defecto.
    assert all(Permission.COMMANDS_IMMOBILIZE.value not in perms for _, perms in module.ROLES.values())
