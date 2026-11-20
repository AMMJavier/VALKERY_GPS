"""Fase 3: eventos, reglas, geocercas y estado de conectividad.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_DT = mysql.DATETIME(fsp=3)
NOW = sa.text("(utc_timestamp(3))")
TABLE_OPTS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}


def upgrade() -> None:
    op.add_column(
        "device_states",
        sa.Column("reported_offline", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "geofences",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("geofence_type", sa.String(10), nullable=False),
        sa.Column("center_lat", mysql.DOUBLE(asdecimal=False), nullable=True),
        sa.Column("center_lon", mysql.DOUBLE(asdecimal=False), nullable=True),
        sa.Column("radius_m", sa.Integer(), nullable=True),
        sa.Column("points", sa.JSON(), nullable=True),
        sa.Column("device_id", sa.BigInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", UTC_DT, server_default=NOW, nullable=False),
        sa.Column("updated_at", UTC_DT, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_geofences"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_geofences_device_id_devices", ondelete="CASCADE"
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_geofences_device_id", "geofences", ["device_id"])

    op.create_table(
        "device_geofences",
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("geofence_id", sa.BigInteger(), nullable=False),
        sa.Column("inside", sa.Boolean(), nullable=False),
        sa.Column("changed_at", UTC_DT, nullable=False),
        sa.Column("position_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("device_id", "geofence_id", name="pk_device_geofences"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_device_geofences_device_id_devices", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["geofence_id"],
            ["geofences.id"],
            name="fk_device_geofences_geofence_id_geofences",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["positions.id"],
            name="fk_device_geofences_position_id_positions",
            ondelete="SET NULL",
        ),
        **TABLE_OPTS,
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("position_id", sa.BigInteger(), nullable=True),
        sa.Column("geofence_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("occurred_at", UTC_DT, nullable=False),
        sa.Column("created_at", UTC_DT, nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("dedup_key", mysql.BINARY(32), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.UniqueConstraint("device_id", "dedup_key", name="uq_events_device_id_dedup_key"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_events_device_id_devices", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["position_id"], ["positions.id"], name="fk_events_position_id_positions", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["geofence_id"], ["geofences.id"], name="fk_events_geofence_id_geofences", ondelete="SET NULL"
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_events_device_id_occurred_at", "events", ["device_id", "occurred_at"])
    op.create_index("ix_events_event_type_occurred_at", "events", ["event_type", "occurred_at"])
    op.create_index("ix_events_position_id", "events", ["position_id"])
    op.create_index("ix_events_geofence_id", "events", ["geofence_id"])

    op.create_table(
        "event_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("severity", sa.String(10), nullable=True),
        sa.Column("created_at", UTC_DT, server_default=NOW, nullable=False),
        sa.Column("updated_at", UTC_DT, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_event_rules"),
        sa.UniqueConstraint("event_type", "device_id", name="uq_event_rules_event_type_device_id"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_event_rules_device_id_devices", ondelete="CASCADE"
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_event_rules_device_id", "event_rules", ["device_id"])


def downgrade() -> None:
    op.drop_table("event_rules")
    op.drop_table("events")
    op.drop_table("device_geofences")
    op.drop_table("geofences")
    op.drop_column("device_states", "reported_offline")
