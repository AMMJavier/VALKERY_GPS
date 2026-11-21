"""Contraseñas (Argon2), tokens JWT y bloqueo por intentos fallidos.

El JWT lleva el id de usuario (sub) y su token_version (ver): si la versión
del usuario cambia (contraseña nueva, deshabilitado, roles modificados), todos
los tokens anteriores dejan de valer.

Referencia Traccar: api/security/LoginService.java, api/signature/TokenManager.java
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from .config import ApiSettings

_hasher = PasswordHash.recommended()

# Hash de una contraseña aleatoria para igualar el tiempo de respuesta cuando
# el usuario no existe (evita distinguir usuarios por tiempo).
_DUMMY_HASH = _hasher.hash("valkery-dummy-password-for-timing")

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)


def create_access_token(user_id: int, token_version: int, settings: ApiSettings) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.jwt_expire_min)
    payload = {"sub": str(user_id), "ver": token_version, "iat": now, "exp": expires, "typ": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires


class InvalidToken(Exception):
    pass


def decode_access_token(token: str, settings: ApiSettings) -> tuple[int, int, datetime]:
    """Devuelve (user_id, token_version, expira)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "ver", "exp", "iat"]},
        )
        if payload.get("typ") != "access":
            raise InvalidToken("tipo de token inválido")
        return int(payload["sub"]), int(payload["ver"]), datetime.fromtimestamp(payload["exp"], UTC)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidToken(str(exc)) from exc


class LoginGuard:
    """Bloquea un usuario tras N intentos fallidos en una ventana de tiempo.

    En memoria: vale para un solo proceso de la API (el despliegue previsto).
    """

    def __init__(self, max_attempts: int, lockout_s: float) -> None:
        self.max_attempts = max_attempts
        self.lockout_s = lockout_s
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        attempts = self._failures[key]
        while attempts and now - attempts[0] > self.lockout_s:
            attempts.popleft()
        return attempts

    def is_locked(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) >= self.max_attempts

    def failure(self, key: str) -> None:
        now = time.monotonic()
        self._prune(key, now).append(now)

    def success(self, key: str) -> None:
        self._failures.pop(key, None)
