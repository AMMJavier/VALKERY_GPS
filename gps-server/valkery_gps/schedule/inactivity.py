"""DEVICE_OFFLINE por tiempo sin comunicación.

Se basa en last_seen (cualquier trama del equipo), NO en ignition ni en que la
conexión TCP esté abierta: un equipo puede cerrar y reabrir conexiones con
normalidad. Se avisa una sola vez (reported_offline); la siguiente
comunicación genera DEVICE_ONLINE (handlers/database.py).

Referencia Traccar: schedule/TaskDeviceInactivityCheck.java
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from valkery_core.enums import EventType
from valkery_core.models import Device, DeviceState

from ..handlers.events.engine import connectivity_event

logger = logging.getLogger(__name__)


async def check_inactivity(
    session_factory: async_sessionmaker[AsyncSession], offline_after_s: int, now: datetime | None = None
) -> int:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=offline_after_s)
    async with session_factory.begin() as db:
        states = (
            await db.scalars(
                select(DeviceState)
                .join(Device, Device.id == DeviceState.device_id)
                .where(
                    Device.enabled.is_(True),
                    DeviceState.reported_offline.is_(False),
                    DeviceState.last_seen.is_not(None),
                    DeviceState.last_seen < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        for state in states:
            state.reported_offline = True
            await connectivity_event(
                db,
                state.device_id,
                EventType.DEVICE_OFFLINE,
                now,
                {"last_seen": state.last_seen.isoformat(), "offline_after_s": offline_after_s},
            )
        return len(states)


async def inactivity_loop(
    session_factory: async_sessionmaker[AsyncSession], offline_after_s: int, interval_s: int
) -> None:
    while True:
        try:
            count = await check_inactivity(session_factory, offline_after_s)
            if count:
                logger.info("Inactividad: %d dispositivo(s) sin comunicación", count)
        except Exception:
            logger.exception("Fallo en la verificación de inactividad")
        await asyncio.sleep(interval_s)
