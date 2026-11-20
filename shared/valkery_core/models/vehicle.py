"""vehicles: entidades rastreadas (la moto).

owner_id se agrega en la fase 4, cuando exista la tabla users.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, IdMixin, TimestampMixin


class Vehicle(IdMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"

    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(30), nullable=False, default="motorcycle")
    plate: Mapped[str | None] = mapped_column(String(20))
