"""Historial de posiciones paginado por rango de fechas.

GET /devices/{id}/positions?from=...&to=...&limit=500&cursor=...&valid_only=true

- Rango obligatorio [from, to) con un máximo de VALKERY_API_POSITIONS_MAX_RANGE_DAYS.
- Orden cronológico por gps_time (hora del GPS, no de recepción).
- Paginación por cursor: next_cursor = null cuando no hay más.

Referencia Traccar: api/resource/PositionResource.java
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select

from valkery_core.enums import Permission
from valkery_core.models import Position

from ...core.deps import CurrentUser, DbSession, Settings, require
from ...repositories.pagination import decode_cursor, encode_cursor
from ...schemas import AwareDatetime, Page, PositionOut
from .devices import get_device_or_404

router = APIRouter(tags=["positions"])
Reader = Annotated[CurrentUser, Depends(require(Permission.POSITIONS_READ))]


@router.get("/devices/{device_id}/positions", response_model=Page[PositionOut])
async def list_positions(
    device_id: int,
    _: Reader,
    db: DbSession,
    settings: Settings,
    from_: Annotated[AwareDatetime, Query(alias="from")],
    to: AwareDatetime,
    limit: Annotated[int, Query(ge=1)] = 500,
    cursor: str | None = None,
    valid_only: bool = False,
    include_io: bool = False,
) -> Page[PositionOut]:
    if to <= from_:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="'to' debe ser posterior a 'from'")
    if to - from_ > timedelta(days=settings.positions_max_range_days):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"El rango máximo es de {settings.positions_max_range_days} días",
        )
    limit = min(limit, settings.page_max)
    await get_device_or_404(db, device_id)

    query = select(Position).where(
        Position.device_id == device_id, Position.gps_time >= from_, Position.gps_time < to
    )
    if valid_only:
        query = query.where(Position.valid.is_(True))
    if cursor:
        at, last_id = decode_cursor(cursor)
        query = query.where(or_(Position.gps_time > at, and_(Position.gps_time == at, Position.id > last_id)))
    rows = list((await db.scalars(query.order_by(Position.gps_time, Position.id).limit(limit + 1))).all())

    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for p in rows:
        item = PositionOut.model_validate(p)
        if not include_io:
            item.io = None
        items.append(item)
    next_cursor = encode_cursor(rows[-1].gps_time, rows[-1].id) if has_more else None
    return Page[PositionOut](items=items, next_cursor=next_cursor)
