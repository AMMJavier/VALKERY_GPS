"""Motor de eventos: ejecuta los detectores, aplica reglas y persiste.

Se ejecuta dentro de la MISMA transacción que guarda las posiciones: si algo
falla, se revierte todo y no se envía ACK (el equipo reintenta). Solo procesa
posiciones NUEVAS, de modo que una retransmisión no repite eventos; además
events.dedup_key es UNIQUE como segunda barrera.

Referencia Traccar: BasePipelineFactory (eventHandlers), database/NotificationManager.java
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from valkery_core.db.base import utcnow
from valkery_core.enums import DEFAULT_SEVERITY, EventSource, EventType, GeofenceType
from valkery_core.models import DeviceGeofence, Event, EventRule, Geofence

from .alarm import detect_alarms
from .base import EventCandidate, EventSettings, PreviousState
from .geofence import FenceShape, detect_geofences
from .ignition import detect_ignition

logger = logging.getLogger(__name__)


class RuleBook:
    """Reglas por tipo: la específica del dispositivo gana a la global."""

    def __init__(self, rules: list[EventRule], device_id: int) -> None:
        self._rules: dict[str, EventRule] = {}
        for rule in sorted(rules, key=lambda r: r.device_id is not None):
            if rule.device_id in (None, device_id):
                self._rules[rule.event_type] = rule

    def severity_for(self, event_type: EventType) -> str | None:
        """Severidad a usar, o None si el tipo está deshabilitado."""
        rule = self._rules.get(event_type.value)
        if rule is not None and not rule.enabled:
            return None
        if rule is not None and rule.severity:
            return rule.severity
        return DEFAULT_SEVERITY[event_type].value


async def load_rules(db: AsyncSession, device_id: int) -> RuleBook:
    rules = (
        await db.scalars(select(EventRule).where(or_(EventRule.device_id.is_(None), EventRule.device_id == device_id)))
    ).all()
    return RuleBook(list(rules), device_id)


async def store_events(db: AsyncSession, device_id: int, candidates: list[EventCandidate]) -> list[EventCandidate]:
    """Aplica reglas e inserta. Devuelve los candidatos efectivamente aceptados."""
    if not candidates:
        return []
    rules = await load_rules(db, device_id)
    rows: list[dict[str, Any]] = []
    accepted: list[EventCandidate] = []
    now = utcnow()
    for c in candidates:
        severity = rules.severity_for(c.event_type)
        if severity is None:
            continue
        accepted.append(c)
        rows.append(
            {
                "device_id": device_id,
                "position_id": c.position_id,
                "geofence_id": c.geofence_id,
                "event_type": c.event_type.value,
                "severity": severity,
                "source": c.source.value,
                "occurred_at": c.occurred_at,
                "created_at": now,
                "attributes": c.attributes,
                "dedup_key": c.dedup_key(),
            }
        )
    if rows:
        stmt = insert(Event).values(rows)
        await db.execute(stmt.on_duplicate_key_update(id=Event.__table__.c.id))
        for c in accepted:
            logger.info("Evento %s dispositivo %d a las %s", c.event_type.value, device_id, c.occurred_at.isoformat())
    return accepted


async def connectivity_event(
    db: AsyncSession, device_id: int, event_type: EventType, at: datetime, attributes: dict[str, Any]
) -> None:
    await store_events(
        db,
        device_id,
        [EventCandidate(event_type=event_type, source=EventSource.PLATFORM, occurred_at=at, attributes=attributes)],
    )


def _shape(g: Geofence) -> FenceShape:
    kind = GeofenceType(g.geofence_type)
    if kind == GeofenceType.CIRCLE:
        return FenceShape(g.id, g.name, kind, center=(g.center_lat, g.center_lon), radius_m=float(g.radius_m))
    return FenceShape(g.id, g.name, kind, polygon=tuple((float(p[0]), float(p[1])) for p in g.points or []))


class EventEngine:
    def __init__(self, settings: EventSettings) -> None:
        self.settings = settings

    async def process(
        self, db: AsyncSession, device_id: int, new_rows: list[dict[str, Any]], previous: PreviousState
    ) -> list[EventCandidate]:
        if not new_rows:
            return []
        candidates: list[EventCandidate] = []
        candidates += detect_ignition(new_rows, previous, self.settings.ignition_max_gap)
        candidates += detect_alarms(new_rows)
        candidates += await self._geofences(db, device_id, new_rows, previous)
        candidates.sort(key=lambda c: c.occurred_at)
        return await store_events(db, device_id, candidates)

    async def _geofences(
        self, db: AsyncSession, device_id: int, rows: list[dict[str, Any]], previous: PreviousState
    ) -> list[EventCandidate]:
        if not any(r["valid"] for r in rows):
            return []
        fences = (
            await db.scalars(
                select(Geofence).where(
                    Geofence.enabled.is_(True), or_(Geofence.device_id.is_(None), Geofence.device_id == device_id)
                )
            )
        ).all()
        if not fences:
            return []
        state_rows = {
            s.geofence_id: s
            for s in (
                await db.scalars(
                    select(DeviceGeofence).where(DeviceGeofence.device_id == device_id).with_for_update()
                )
            ).all()
        }
        events, updates = detect_geofences(
            rows,
            [_shape(f) for f in fences],
            {gid: s.inside for gid, s in state_rows.items()},
            previous.fix_time,
            self.settings.geofence_margin_m,
        )
        for geofence_id, t in updates.items():
            row = state_rows.get(geofence_id)
            if row is None:
                db.add(
                    DeviceGeofence(
                        device_id=device_id,
                        geofence_id=geofence_id,
                        inside=t.inside,
                        changed_at=t.gps_time,
                        position_id=t.position_id,
                    )
                )
            else:
                row.inside, row.changed_at, row.position_id = t.inside, t.gps_time, t.position_id
        return events
