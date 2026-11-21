"""Consulta de auditoría (requiere audit:read)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select

from valkery_core.enums import Permission
from valkery_core.models import AuditLog

from ...core.deps import CurrentUser, DbSession, Settings, require
from ...repositories.pagination import decode_cursor, encode_cursor
from ...schemas import AuditOut, Page

router = APIRouter(prefix="/audit", tags=["audit"])
Reader = Annotated[CurrentUser, Depends(require(Permission.AUDIT_READ))]


@router.get("", response_model=Page[AuditOut])
async def list_audit(
    _: Reader,
    db: DbSession,
    settings: Settings,
    action: str | None = None,
    actor_id: int | None = None,
    limit: Annotated[int, Query(ge=1)] = 100,
    cursor: str | None = None,
) -> Page[AuditOut]:
    limit = min(limit, settings.page_max)
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if actor_id is not None:
        query = query.where(AuditLog.actor_id == actor_id)
    if cursor:
        at, last_id = decode_cursor(cursor)
        query = query.where(or_(AuditLog.created_at < at, and_(AuditLog.created_at == at, AuditLog.id < last_id)))
    rows = list(
        (await db.scalars(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1))).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if has_more else None
    return Page[AuditOut](items=[AuditOut.model_validate(r) for r in rows], next_cursor=next_cursor)
