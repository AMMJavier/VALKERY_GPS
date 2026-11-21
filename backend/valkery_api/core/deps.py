"""Dependencias FastAPI: sesión de base de datos, usuario actual y permisos.

Referencia Traccar: api/security/SecurityRequestFilter.java, PermissionsService.java
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from valkery_core.enums import Permission
from valkery_core.models import RolePermission, User, UserRole

from .config import ApiSettings
from .security import InvalidToken, decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> ApiSettings:
    return request.app.state.settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
Settings = Annotated[ApiSettings, Depends(get_settings)]


@dataclass(slots=True)
class CurrentUser:
    user: User
    permissions: frozenset[str]

    @property
    def id(self) -> int:
        return self.user.id

    def has(self, permission: Permission) -> bool:
        return permission.value in self.permissions


async def load_permissions(db: AsyncSession, user_id: int) -> frozenset[str]:
    rows = await db.scalars(
        select(RolePermission.permission)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    return frozenset(rows.all())


UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales inválidas o sesión expirada",
    headers={"WWW-Authenticate": "Bearer"},
)


async def authenticate_token(db: AsyncSession, token: str, settings: ApiSettings) -> CurrentUser:
    try:
        user_id, version, _ = decode_access_token(token, settings)
    except InvalidToken:
        raise UNAUTHORIZED from None
    user = await db.get(User, user_id)
    if user is None or not user.enabled or user.token_version != version:
        raise UNAUTHORIZED
    return CurrentUser(user=user, permissions=await load_permissions(db, user.id))


async def get_current_user(
    db: DbSession,
    settings: Settings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UNAUTHORIZED
    return await authenticate_token(db, credentials.credentials, settings)


Authenticated = Annotated[CurrentUser, Depends(get_current_user)]


def require(*permissions: Permission) -> Callable[..., CurrentUser]:
    """Dependencia que exige TODOS los permisos indicados."""

    async def checker(current: Authenticated) -> CurrentUser:
        missing = [p.value for p in permissions if not current.has(p)]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Permiso requerido: {', '.join(missing)}")
        return current

    return checker


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
