"""Casos de uso de usuarios y roles."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from valkery_core.models import Role, RolePermission, User, UserRole

from ..core.security import hash_password
from ..schemas import UserOut


async def roles_by_name(db: AsyncSession, names: list[str]) -> list[Role]:
    unique = sorted(set(names))
    roles = (await db.scalars(select(Role).where(Role.name.in_(unique)))).all()
    missing = set(unique) - {r.name for r in roles}
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"roles inexistentes: {sorted(missing)}")
    return list(roles)


async def set_roles(db: AsyncSession, user: User, names: list[str]) -> None:
    roles = await roles_by_name(db, names)
    await db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    db.add_all(UserRole(user_id=user.id, role_id=r.id) for r in roles)


async def user_roles(db: AsyncSession, user_id: int) -> list[str]:
    rows = await db.scalars(
        select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    )
    return sorted(rows.all())


async def user_out(db: AsyncSession, user: User) -> UserOut:
    roles = await user_roles(db, user.id)
    perms = await db.scalars(
        select(RolePermission.permission)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user.id)
        .distinct()
    )
    out = UserOut.model_validate(user)
    out.roles = roles
    out.permissions = sorted(perms.all())
    return out


async def create_user(
    db: AsyncSession, *, username: str, password: str, roles: list[str], full_name: str = "", email: str | None = None
) -> User:
    if await db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="el nombre de usuario ya existe")
    if email and await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="el email ya está en uso")
    user = User(
        username=username,
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        enabled=True,
        token_version=0,
    )
    db.add(user)
    await db.flush()
    await set_roles(db, user, roles)
    return user


async def count_admins(db: AsyncSession, excluding_user_id: int | None = None) -> int:
    query = (
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.name == "admin", User.enabled.is_(True))
    )
    if excluding_user_id is not None:
        query = query.where(User.id != excluding_user_id)
    return len((await db.scalars(query)).all())
