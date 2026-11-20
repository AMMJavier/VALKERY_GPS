"""device_states: último estado conocido de cada dispositivo (una fila por equipo).

- Los campos de posición (fix_*) solo se actualizan con posiciones válidas.
- Los campos de telemetría se toman del registro con gps_time más reciente,
  aunque el equipo envíe registros antiguos de su memoria después.
- last_seen es la última vez que el equipo se comunicó (cualquier trama).
- online = hay una conexión TCP abierta; reported_offline = se avisó DEVICE_OFFLINE.

Referencia Traccar: Device.positionId + session/state/*
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, SmallInteger, false
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, UtcDateTime


class DeviceState(Base):
    __tablename__ = "device_states"

    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    last_seen: Mapped[datetime | None] = mapped_column(UtcDateTime())
    # True desde que se emitió DEVICE_OFFLINE hasta la siguiente comunicación (DEVICE_ONLINE).
    reported_offline: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # Último registro recibido (por gps_time)
    last_position_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("positions.id", ondelete="SET NULL")
    )
    last_gps_time: Mapped[datetime | None] = mapped_column(UtcDateTime())
    ignition: Mapped[bool | None] = mapped_column(Boolean)
    movement: Mapped[bool | None] = mapped_column(Boolean)
    dout1: Mapped[bool | None] = mapped_column(Boolean)
    gnss_status: Mapped[int | None] = mapped_column(SmallInteger)
    gsm_signal: Mapped[int | None] = mapped_column(SmallInteger)
    external_voltage_mv: Mapped[int | None] = mapped_column(Integer)
    battery_voltage_mv: Mapped[int | None] = mapped_column(Integer)
    odometer_m: Mapped[int | None] = mapped_column(BigInteger)

    # Última posición válida
    fix_position_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("positions.id", ondelete="SET NULL")
    )
    fix_time: Mapped[datetime | None] = mapped_column(UtcDateTime())
    latitude: Mapped[float | None] = mapped_column(DOUBLE(asdecimal=False))
    longitude: Mapped[float | None] = mapped_column(DOUBLE(asdecimal=False))
    speed: Mapped[int | None] = mapped_column(SmallInteger)
    course: Mapped[int | None] = mapped_column(SmallInteger)
