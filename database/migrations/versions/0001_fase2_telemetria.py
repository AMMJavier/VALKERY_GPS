"""Fase 2: vehículos, dispositivos, sesiones, tramas, posiciones y estado actual.

Revision ID: 0001
Revises:
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_DT = mysql.DATETIME(fsp=3)
NOW = sa.text("(utc_timestamp(3))")
TABLE_OPTS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("alias", sa.String(100), nullable=False),
        sa.Column("vehicle_type", sa.String(30), nullable=False),
        sa.Column("plate", sa.String(20), nullable=True),
        sa.Column("created_at", UTC_DT, server_default=NOW, nullable=False),
        sa.Column("updated_at", UTC_DT, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_vehicles"),
        **TABLE_OPTS,
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("imei", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("brand", sa.String(50), nullable=False),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("fw_version", sa.String(50), nullable=True),
        sa.Column("vehicle_id", sa.BigInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", UTC_DT, server_default=NOW, nullable=False),
        sa.Column("updated_at", UTC_DT, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.UniqueConstraint("imei", name="uq_devices_imei"),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicles.id"], name="fk_devices_vehicle_id_vehicles", ondelete="SET NULL"
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_devices_vehicle_id", "devices", ["vehicle_id"])

    op.create_table(
        "device_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("transport", sa.String(10), nullable=False),
        sa.Column("remote_addr", sa.String(64), nullable=False),
        sa.Column("connected_at", UTC_DT, nullable=False),
        sa.Column("disconnected_at", UTC_DT, nullable=True),
        sa.Column("close_reason", sa.String(255), nullable=True),
        sa.Column("packets", sa.Integer(), nullable=False),
        sa.Column("records", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_device_sessions"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_device_sessions_device_id_devices", ondelete="CASCADE"
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_device_sessions_device_id_connected_at", "device_sessions", ["device_id", "connected_at"])

    op.create_table(
        "raw_packets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("received_at", UTC_DT, nullable=False),
        sa.Column("codec", sa.SmallInteger(), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("payload", mysql.MEDIUMBLOB(), nullable=False),
        sa.Column("digest", mysql.BINARY(32), nullable=False),
        sa.Column("parse_status", sa.String(20), nullable=False),
        sa.Column("error", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_raw_packets"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_raw_packets_device_id_devices", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["device_sessions.id"],
            name="fk_raw_packets_session_id_device_sessions",
            ondelete="SET NULL",
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_raw_packets_device_id", "raw_packets", ["device_id"])
    op.create_index("ix_raw_packets_session_id", "raw_packets", ["session_id"])
    op.create_index("ix_raw_packets_received_at", "raw_packets", ["received_at"])

    op.create_table(
        "positions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_packet_id", sa.BigInteger(), nullable=True),
        sa.Column("gps_time", UTC_DT, nullable=False),
        sa.Column("received_at", UTC_DT, nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("latitude", mysql.DOUBLE(), nullable=False),
        sa.Column("longitude", mysql.DOUBLE(), nullable=False),
        sa.Column("altitude", sa.SmallInteger(), nullable=False),
        sa.Column("speed", sa.SmallInteger(), nullable=False),
        sa.Column("course", sa.SmallInteger(), nullable=False),
        sa.Column("satellites", sa.SmallInteger(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("event_io_id", sa.Integer(), nullable=False),
        sa.Column("ignition", sa.Boolean(), nullable=True),
        sa.Column("movement", sa.Boolean(), nullable=True),
        sa.Column("dout1", sa.Boolean(), nullable=True),
        sa.Column("gnss_status", sa.SmallInteger(), nullable=True),
        sa.Column("gsm_signal", sa.SmallInteger(), nullable=True),
        sa.Column("external_voltage_mv", sa.Integer(), nullable=True),
        sa.Column("battery_voltage_mv", sa.Integer(), nullable=True),
        sa.Column("odometer_m", sa.BigInteger(), nullable=True),
        sa.Column("io", sa.JSON(), nullable=False),
        sa.Column("dedup_key", mysql.BINARY(32), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_positions"),
        sa.UniqueConstraint("device_id", "dedup_key", name="uq_positions_device_id_dedup_key"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_positions_device_id_devices", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["raw_packet_id"], ["raw_packets.id"], name="fk_positions_raw_packet_id_raw_packets", ondelete="SET NULL"
        ),
        **TABLE_OPTS,
    )
    op.create_index("ix_positions_device_id_gps_time", "positions", ["device_id", "gps_time"])
    op.create_index("ix_positions_raw_packet_id", "positions", ["raw_packet_id"])

    op.create_table(
        "device_states",
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("online", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_seen", UTC_DT, nullable=True),
        sa.Column("last_position_id", sa.BigInteger(), nullable=True),
        sa.Column("last_gps_time", UTC_DT, nullable=True),
        sa.Column("ignition", sa.Boolean(), nullable=True),
        sa.Column("movement", sa.Boolean(), nullable=True),
        sa.Column("dout1", sa.Boolean(), nullable=True),
        sa.Column("gnss_status", sa.SmallInteger(), nullable=True),
        sa.Column("gsm_signal", sa.SmallInteger(), nullable=True),
        sa.Column("external_voltage_mv", sa.Integer(), nullable=True),
        sa.Column("battery_voltage_mv", sa.Integer(), nullable=True),
        sa.Column("odometer_m", sa.BigInteger(), nullable=True),
        sa.Column("fix_position_id", sa.BigInteger(), nullable=True),
        sa.Column("fix_time", UTC_DT, nullable=True),
        sa.Column("latitude", mysql.DOUBLE(), nullable=True),
        sa.Column("longitude", mysql.DOUBLE(), nullable=True),
        sa.Column("speed", sa.SmallInteger(), nullable=True),
        sa.Column("course", sa.SmallInteger(), nullable=True),
        sa.PrimaryKeyConstraint("device_id", name="pk_device_states"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_device_states_device_id_devices", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["last_position_id"],
            ["positions.id"],
            name="fk_device_states_last_position_id_positions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["fix_position_id"],
            ["positions.id"],
            name="fk_device_states_fix_position_id_positions",
            ondelete="SET NULL",
        ),
        **TABLE_OPTS,
    )


def downgrade() -> None:
    op.drop_table("device_states")
    op.drop_table("positions")
    op.drop_table("raw_packets")
    op.drop_table("device_sessions")
    op.drop_table("devices")
    op.drop_table("vehicles")
