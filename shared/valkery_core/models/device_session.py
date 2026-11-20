"""device_sessions: cada conexión TCP de un equipo, de la autenticación al cierre."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, UtcDateTime


class DeviceSessionRecord(IdMixin, Base):
    __tablename__ = "device_sessions"
    __table_args__ = (Index(None, "device_id", "connected_at"),)

    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    transport: Mapped[str] = mapped_column(String(10), nullable=False)
    remote_addr: Mapped[str] = mapped_column(String(64), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    disconnected_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    close_reason: Mapped[str | None] = mapped_column(String(255))
    packets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
