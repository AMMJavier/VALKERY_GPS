"""Eventos (más recientes primero) y reglas de eventos.

Referencia Traccar: api/resource/EventResource.java, NotificationResource.java
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, or_, select

from valkery_core.enums import EventType, Permission, Severity
from valkery_core.models import Device, Event, EventRule

from ...core.deps import CurrentUser, DbSession, Settings, require
from ...repositories.pagination import decode_cursor, encode_cursor
from ...schemas import AwareDatetime, EventOut, EventRuleIn, EventRuleOut, Page
from ...services.audit import audit

router = APIRouter(tags=["events"])
Reader = Annotated[CurrentUser, Depends(require(Permission.EVENTS_READ))]
RulesManager = Annotated[CurrentUser, Depends(require(Permission.EVENT_RULES_MANAGE))]


@router.get("/events", response_model=Page[EventOut])
async def list_events(
    _: Reader,
    db: DbSession,
    settings: Settings,
    device_id: int | None = None,
    event_type: Annotated[list[EventType] | None, Query()] = None,
    severity: Severity | None = None,
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1)] = 100,
    cursor: str | None = None,
) -> Page[EventOut]:
    limit = min(limit, settings.page_max)
    query = select(Event)
    if device_id is not None:
        query = query.where(Event.device_id == device_id)
    if event_type:
        query = query.where(Event.event_type.in_([t.value for t in event_type]))
    if severity is not None:
        query = query.where(Event.severity == severity.value)
    if from_ is not None:
        query = query.where(Event.occurred_at >= from_)
    if to is not None:
        query = query.where(Event.occurred_at < to)
    if cursor:
        at, last_id = decode_cursor(cursor)
        query = query.where(or_(Event.occurred_at < at, and_(Event.occurred_at == at, Event.id < last_id)))
    rows = list((await db.scalars(query.order_by(Event.occurred_at.desc(), Event.id.desc()).limit(limit + 1))).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].occurred_at, rows[-1].id) if has_more else None
    return Page[EventOut](items=[EventOut.model_validate(e) for e in rows], next_cursor=next_cursor)


@router.get("/event-rules", response_model=list[EventRuleOut])
async def list_rules(_: Reader, db: DbSession) -> list[EventRule]:
    return list((await db.scalars(select(EventRule).order_by(EventRule.event_type, EventRule.id))).all())


@router.put("/event-rules", response_model=EventRuleOut)
async def upsert_rule(body: EventRuleIn, current: RulesManager, db: DbSession, request: Request) -> EventRule:
    """Crea o reemplaza la regla de (event_type, device_id)."""
    if body.device_id is not None and await db.get(Device, body.device_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="device_id inexistente")
    scope = EventRule.device_id.is_(None) if body.device_id is None else EventRule.device_id == body.device_id
    rule = await db.scalar(select(EventRule).where(EventRule.event_type == body.event_type.value, scope))
    if rule is None:
        rule = EventRule(event_type=body.event_type.value, device_id=body.device_id)
        db.add(rule)
    rule.enabled = body.enabled
    rule.severity = body.severity.value if body.severity else None
    await db.flush()
    audit(
        db,
        actor_id=current.id,
        action="event_rule_set",
        request=request,
        target_type="event_rule",
        target_id=rule.id,
        details=body.model_dump(mode="json"),
    )
    await db.commit()
    return rule


@router.delete("/event-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, current: RulesManager, db: DbSession, request: Request) -> None:
    rule = await db.get(EventRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Regla inexistente")
    await db.delete(rule)
    audit(db, actor_id=current.id, action="event_rule_deleted", request=request, target_type="event_rule", target_id=rule_id)
    await db.commit()
