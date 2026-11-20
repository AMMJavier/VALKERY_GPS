"""events y event_rules.

events
    Eventos derivados (transiciones, geocercas, conectividad) o nativos del
    equipo (alarmas). Una posición normal NO genera evento.
    dedup_key (SHA-256 de posición + tipo + geocerca) es UNIQUE por dispositivo
    para eventos ligados a una posición: reprocesar no los duplica. Los eventos
    de conectividad no tienen posición y llevan dedup_key NULL.

event_rules
    Configuración por tipo de evento: habilitar/deshabilitar y cambiar la
    severidad, global (device_id NULL) o para un dispositivo (tiene prioridad).

Referencia Traccar: model/Event.java, model/Notification.java
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, String, UniqueConstraint, true
from sqlalchemy.dialects.mysql import BINARY
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, TimestampMixin, UtcDateTime, utcnow


class Event(IdMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("device_id", "dedup_key"),
        Index(None, "device_id", "occurred_at"),
        Index(None, "event_type", "occurred_at"),
    )

    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    position_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("positions.id", ondelete="SET NULL"), index=True
    )
    geofence_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("geofences.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=utcnow)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    dedup_key: Mapped[bytes | None] = mapped_column(BINARY(32))


class EventRule(IdMixin, TimestampMixin, Base):
    __tablename__ = "event_rules"
    __table_args__ = (UniqueConstraint("event_type", "device_id"),)

    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    device_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    severity: Mapped[str | None] = mapped_column(String(10))
