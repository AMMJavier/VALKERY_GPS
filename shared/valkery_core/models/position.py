"""positions: histórico GPS.

- gps_time es la hora del registro según el equipo; received_at, la del servidor.
- io guarda el mapa I/O original (id -> valor; bytes en hex), sin descartar nada.
- Las columnas de primer nivel (ignition, dout1, voltajes...) se copian de io
  para consultas rápidas.
- dedup_key (SHA-256 del contenido del registro) + device_id es UNIQUE: si el
  equipo retransmite un paquete, los registros repetidos no se duplican.

Referencia Traccar: model/Position.java
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, Integer, SmallInteger, UniqueConstraint
from sqlalchemy.dialects.mysql import BINARY, DOUBLE
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, UtcDateTime


class Position(IdMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("device_id", "dedup_key"),
        Index(None, "device_id", "gps_time"),
    )

    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    raw_packet_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("raw_packets.id", ondelete="SET NULL"), index=True
    )
    gps_time: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)

    valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latitude: Mapped[float] = mapped_column(DOUBLE(asdecimal=False), nullable=False)
    longitude: Mapped[float] = mapped_column(DOUBLE(asdecimal=False), nullable=False)
    altitude: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    speed: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # km/h
    course: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # grados
    satellites: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    event_io_id: Mapped[int] = mapped_column(Integer, nullable=False)

    ignition: Mapped[bool | None] = mapped_column(Boolean)
    movement: Mapped[bool | None] = mapped_column(Boolean)
    dout1: Mapped[bool | None] = mapped_column(Boolean)
    gnss_status: Mapped[int | None] = mapped_column(SmallInteger)
    gsm_signal: Mapped[int | None] = mapped_column(SmallInteger)
    external_voltage_mv: Mapped[int | None] = mapped_column(Integer)
    battery_voltage_mv: Mapped[int | None] = mapped_column(Integer)
    odometer_m: Mapped[int | None] = mapped_column(BigInteger)

    io: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    dedup_key: Mapped[bytes] = mapped_column(BINARY(32), nullable=False)
