"""users, roles, role_permissions y user_roles.

- password_hash: Argon2 (pwdlib). Nunca se guarda la contraseña.
- token_version: se incrementa al cambiar la contraseña, deshabilitar al
  usuario o cambiar sus roles; invalida todos los JWT emitidos antes.
- Los permisos (valkery_core.enums.Permission) se asignan a roles, y los
  roles a usuarios. La inmovilización es un permiso aparte (fase 6).

Referencia Traccar: model/User.java, model/Permission.java
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, TimestampMixin, UtcDateTime


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class Role(IdMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(50), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True, index=True
    )
