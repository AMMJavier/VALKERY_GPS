"""devices: equipo GPS identificado por IMEI.

Solo los dispositivos con enabled=1 pueden conectarse al servidor TCP.

Referencia Traccar: model/Device.java
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, TimestampMixin


class Device(IdMixin, TimestampMixin, Base):
    __tablename__ = "devices"

    imei: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    brand: Mapped[str] = mapped_column(String(50), nullable=False, default="Teltonika")
    model: Mapped[str] = mapped_column(String(50), nullable=False, default="FMC920")
    fw_version: Mapped[str | None] = mapped_column(String(50))
    vehicle_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("vehicles.id", ondelete="SET NULL"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
