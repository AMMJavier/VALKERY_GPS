"""audit_logs: acciones sensibles (inicios de sesión, usuarios, dispositivos,
geocercas, reglas y, en la fase 6, comandos).

actor_id es NULL para intentos de inicio de sesión de usuarios inexistentes.

Referencia Traccar: api/resource/AuditResource.java
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, UtcDateTime, utcnow


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index(None, "created_at"), Index(None, "target_type", "target_id"))

    actor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(30))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=utcnow)
