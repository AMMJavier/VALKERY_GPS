"""Fase 4: usuarios, roles, permisos y auditoría. Crea los roles admin, operator y viewer.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_DT = mysql.DATETIME(fsp=3)
NOW = sa.text("(utc_timestamp(3))")
TABLE_OPTS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}

# Copia fija de valkery_core.enums.DEFAULT_ROLES al momento de esta migración:
# una migración no debe cambiar si el código cambia después.
ROLES = {
    "admin": (
        "Administración completa (sin inmovilización)",
        [
            "devices:read",
            "positions:read",
            "events:read",
            "devices:manage",
            "geofences:manage",
            "event_rules:manage",
            "users:manage",
            "audit:read",
            "commands:send",
        ],
    ),
    "operator": (
        "Monitoreo y gestión de geocercas y reglas",
        ["devices:read", "positions:read", "events:read", "geofences:manage", "event_rules:manage"],
    ),
    "viewer": ("Solo lectura", ["devices:read", "positions:read", "events:read"]),
}


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("last_login_at", UTC_DT, nullable=True),
        sa.Column("created_at", UTC_DT, server_default=NOW, nullable=False),
        sa.Column("updated_at", UTC_DT, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        **TABLE_OPTS,
    )

    roles = op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
        **TABLE_OPTS,
    )

    role_permissions = op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission", sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint("role_id", "permission", name="pk_role_permissions"),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_role_permissions_role_id_roles", ondelete="CASCADE"
        ),
        **TABLE_OPTS,
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "role_id", name="pk_user_roles"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_roles_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name="fk_user_roles_role_id_roles", ondelete="CASCADE"),
        **TABLE_OPTS,
    )
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", UTC_DT, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_audit_logs_actor_id_users", ondelete="SET NULL"
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_target_type_target_id", "audit_logs", ["target_type", "target_id"])

    # Roles iniciales (ids fijos para poder referenciar sus permisos).
    op.bulk_insert(
        roles,
        [{"id": i, "name": name, "description": desc} for i, (name, (desc, _)) in enumerate(ROLES.items(), 1)],
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": i, "permission": perm}
            for i, (_, (_, perms)) in enumerate(ROLES.items(), 1)
            for perm in perms
        ],
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("users")
