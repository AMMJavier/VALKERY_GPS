"""Usuarios y roles (requiere users:manage).

Referencia Traccar: api/resource/UserResource.java
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from valkery_core.enums import Permission
from valkery_core.models import Role, RolePermission, User

from ...core.deps import CurrentUser, DbSession, require
from ...core.security import hash_password
from ...schemas import PasswordReset, RoleOut, UserCreate, UserOut, UserUpdate
from ...services.audit import audit
from ...services.users import count_admins, create_user, set_roles, user_out, user_roles

router = APIRouter(prefix="/users", tags=["users"])
Manager = Annotated[CurrentUser, Depends(require(Permission.USERS_MANAGE))]


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(_: Manager, db: DbSession) -> list[RoleOut]:
    roles = (await db.scalars(select(Role).order_by(Role.id))).all()
    perms = (await db.execute(select(RolePermission.role_id, RolePermission.permission))).all()
    return [
        RoleOut(
            id=r.id,
            name=r.name,
            description=r.description,
            permissions=sorted(p for rid, p in perms if rid == r.id),
        )
        for r in roles
    ]


@router.get("", response_model=list[UserOut])
async def list_users(_: Manager, db: DbSession) -> list[UserOut]:
    users = (await db.scalars(select(User).order_by(User.id))).all()
    return [await user_out(db, u) for u in users]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create(body: UserCreate, current: Manager, db: DbSession, request: Request) -> UserOut:
    user = await create_user(
        db, username=body.username, password=body.password, roles=body.roles, full_name=body.full_name, email=body.email
    )
    audit(
        db,
        actor_id=current.id,
        action="user_created",
        request=request,
        target_type="user",
        target_id=user.id,
        details={"username": user.username, "roles": sorted(set(body.roles))},
    )
    await db.commit()
    return await user_out(db, user)


async def _get(db: DbSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Usuario inexistente")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update(user_id: int, body: UserUpdate, current: Manager, db: DbSession, request: Request) -> UserOut:
    user = await _get(db, user_id)
    changes = body.model_dump(exclude_unset=True)
    revoke = False

    losing_admin = (changes.get("enabled") is False) or (
        "roles" in changes and "admin" not in (changes["roles"] or [])
    )
    if losing_admin and "admin" in await user_roles(db, user.id) and await count_admins(db, user.id) == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No se puede quitar el último administrador activo")

    if "full_name" in changes and changes["full_name"] is not None:
        user.full_name = changes["full_name"]
    if "email" in changes:
        if changes["email"] and await db.scalar(
            select(User.id).where(User.email == changes["email"], User.id != user.id)
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="el email ya está en uso")
        user.email = changes["email"]
    if changes.get("enabled") is not None and changes["enabled"] != user.enabled:
        user.enabled = changes["enabled"]
        revoke = True
    if changes.get("roles") is not None:
        await set_roles(db, user, changes["roles"])
        revoke = True
    if revoke:
        user.token_version += 1

    audit(
        db,
        actor_id=current.id,
        action="user_updated",
        request=request,
        target_type="user",
        target_id=user.id,
        details={k: v for k, v in changes.items()},
    )
    await db.commit()
    return await user_out(db, user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(user_id: int, body: PasswordReset, current: Manager, db: DbSession, request: Request) -> None:
    user = await _get(db, user_id)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    audit(db, actor_id=current.id, action="password_reset", request=request, target_type="user", target_id=user.id)
    await db.commit()
