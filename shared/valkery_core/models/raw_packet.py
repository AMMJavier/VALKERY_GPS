"""raw_packets: copia de cada trama recibida, para trazabilidad y depuración.

Se borran automáticamente tras VALKERY_RAW_PACKET_RETENTION_DAYS días
(gps-server/valkery_gps/schedule/retention.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.mysql import BINARY, MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, UtcDateTime


class RawPacket(IdMixin, Base):
    __tablename__ = "raw_packets"

    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("device_sessions.id", ondelete="SET NULL"), index=True
    )
    received_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, index=True)
    codec: Mapped[int | None] = mapped_column(SmallInteger)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[bytes] = mapped_column(MEDIUMBLOB, nullable=False)
    digest: Mapped[bytes] = mapped_column(BINARY(32), nullable=False)  # SHA-256 del payload
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(255))
