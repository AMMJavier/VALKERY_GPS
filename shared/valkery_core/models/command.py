"""commands y command_responses (ciclo de vida con trazabilidad completa).

commands guarda quién pidió y confirmó, el texto exacto enviado, la trama,
las precondiciones evaluadas, cada marca de tiempo y la evidencia de la
verificación. Una respuesta del equipo NO equivale a éxito físico del relé
(estado VERIFICADO solo con DOUT1 observado en un registro posterior).

Referencia Traccar: model/Command.java, model/QueuedCommand.java (aquí NO hay cola diferida)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.mysql import VARBINARY
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, UtcDateTime


class Command(IdMixin, Base):
    __tablename__ = "commands"
    __table_args__ = (Index(None, "device_id", "requested_at"), Index(None, "status"))

    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(30), nullable=False)
    command_text: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(25), nullable=False)
    expected_dout1: Mapped[bool | None] = mapped_column(Boolean)

    requested_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    confirmed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("device_sessions.id", ondelete="SET NULL")
    )

    requested_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    responded_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())

    sent_frame: Mapped[bytes | None] = mapped_column(VARBINARY(600))
    preconditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(String(255))


class CommandResponse(IdMixin, Base):
    __tablename__ = "command_responses"

    command_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("commands.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_packet_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("raw_packets.id", ondelete="SET NULL")
    )
    received_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)  # ok | error | unmatched
    detail: Mapped[str | None] = mapped_column(String(255))
