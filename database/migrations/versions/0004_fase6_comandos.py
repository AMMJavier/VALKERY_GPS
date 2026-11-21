"""Fase 6: comandos remotos y respuestas del equipo.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_DT = mysql.DATETIME(fsp=3)
TABLE_OPTS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}


def upgrade() -> None:
    op.create_table(
        "commands",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("command_type", sa.String(30), nullable=False),
        sa.Column("command_text", sa.String(255), nullable=False),
        sa.Column("status", sa.String(25), nullable=False),
        sa.Column("expected_dout1", sa.Boolean(), nullable=True),
        sa.Column("requested_by", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("requested_at", UTC_DT, nullable=False),
        sa.Column("expires_at", UTC_DT, nullable=False),
        sa.Column("confirmed_at", UTC_DT, nullable=True),
        sa.Column("sent_at", UTC_DT, nullable=True),
        sa.Column("responded_at", UTC_DT, nullable=True),
        sa.Column("verified_at", UTC_DT, nullable=True),
        sa.Column("finished_at", UTC_DT, nullable=True),
        sa.Column("sent_frame", mysql.VARBINARY(600), nullable=True),
        sa.Column("preconditions", sa.JSON(), nullable=False),
        sa.Column("verification", sa.JSON(), nullable=True),
        sa.Column("failure_reason", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_commands"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_commands_device_id_devices", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name="fk_commands_requested_by_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"], ["users.id"], name="fk_commands_confirmed_by_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["device_sessions.id"], name="fk_commands_session_id_device_sessions", ondelete="SET NULL"
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_commands_device_id_requested_at", "commands", ["device_id", "requested_at"])
    op.create_index("ix_commands_status", "commands", ["status"])
    op.create_index("ix_commands_requested_by", "commands", ["requested_by"])

    op.create_table(
        "command_responses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("command_id", sa.BigInteger(), nullable=True),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_packet_id", sa.BigInteger(), nullable=True),
        sa.Column("received_at", UTC_DT, nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("detail", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_command_responses"),
        sa.ForeignKeyConstraint(
            ["command_id"], ["commands.id"], name="fk_command_responses_command_id_commands", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_command_responses_device_id_devices", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["raw_packet_id"],
            ["raw_packets.id"],
            name="fk_command_responses_raw_packet_id_raw_packets",
            ondelete="SET NULL",
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_command_responses_command_id", "command_responses", ["command_id"])
    op.create_index("ix_command_responses_device_id", "command_responses", ["device_id"])


def downgrade() -> None:
    op.drop_table("command_responses")
    op.drop_table("commands")
