"""geofences y device_geofences.

geofences
    Zonas de la plataforma: círculo (centro + radio en metros) o polígono
    (lista de [lat, lon]). device_id NULL = aplica a todos los dispositivos.

device_geofences
    Último estado conocido (dentro/fuera) de cada dispositivo respecto de cada
    geocerca. Sin fila = estado desconocido: la primera evaluación solo fija el
    estado, sin generar evento.

Referencia Traccar: model/Geofence.java, handler/GeofenceHandler.java
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Integer, String, true
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, TimestampMixin, UtcDateTime


class Geofence(IdMixin, TimestampMixin, Base):
    __tablename__ = "geofences"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    geofence_type: Mapped[str] = mapped_column(String(10), nullable=False)
    center_lat: Mapped[float | None] = mapped_column(DOUBLE(asdecimal=False))
    center_lon: Mapped[float | None] = mapped_column(DOUBLE(asdecimal=False))
    radius_m: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[list[list[float]] | None] = mapped_column(JSON)
    device_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())


class DeviceGeofence(Base):
    __tablename__ = "device_geofences"

    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    geofence_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geofences.id", ondelete="CASCADE"), primary_key=True
    )
    inside: Mapped[bool] = mapped_column(Boolean, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    position_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("positions.id", ondelete="SET NULL")
    )

