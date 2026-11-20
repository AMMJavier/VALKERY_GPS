"""Borra raw_packets más antiguos que VALKERY_RAW_PACKET_RETENTION_DAYS.

Borra en lotes para no bloquear la tabla. Las posiciones se conservan
(su raw_packet_id queda en NULL por la FK ON DELETE SET NULL).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from valkery_core.models import RawPacket

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000
INTERVAL_S = 3600


async def purge_raw_packets(session_factory: async_sessionmaker[AsyncSession], retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    total = 0
    while True:
        async with session_factory.begin() as db:
            ids = (
                await db.scalars(select(RawPacket.id).where(RawPacket.received_at < cutoff).limit(BATCH_SIZE))
            ).all()
            if not ids:
                return total
            await db.execute(delete(RawPacket).where(RawPacket.id.in_(ids)))
            total += len(ids)


async def retention_loop(session_factory: async_sessionmaker[AsyncSession], retention_days: int) -> None:
    while True:
        try:
            deleted = await purge_raw_packets(session_factory, retention_days)
            if deleted:
                logger.info("Retención: %d tramas antiguas borradas", deleted)
        except Exception:
            logger.exception("Fallo en la tarea de retención")
        await asyncio.sleep(INTERVAL_S)
