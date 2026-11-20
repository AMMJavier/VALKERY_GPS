"""DeclarativeBase, tipo de fecha UTC y mixins.

Todas las fechas se guardan en UTC en columnas DATETIME(3) de MySQL (sin zona)
y se devuelven como datetime con tzinfo=UTC.

Referencia Traccar: model/BaseModel.java
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, MetaData, func
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UtcDateTime(TypeDecorator[datetime]):
    """DATETIME(3) que exige y devuelve datetimes con zona UTC."""

    impl = DATETIME(fsp=3)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("se requiere datetime con zona horaria (UTC)")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, sort_order=-100)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utcnow, server_default=func.utc_timestamp(3), sort_order=100
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=utcnow, onupdate=utcnow, server_default=func.utc_timestamp(3), sort_order=100
    )
