"""Estado de una conexión TCP autenticada con un equipo.

Referencia Traccar: session/DeviceSession.java
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(eq=False, slots=True)
class DeviceSession:
    imei: str
    device_id: int
    peer: str
    writer: asyncio.StreamWriter = field(repr=False)
    transport: str = "tcp"
    connected_at: datetime = field(default_factory=utcnow)
    last_seen: datetime = field(default_factory=utcnow)
    packets_received: int = 0
    records_received: int = 0
    record_id: int | None = None  # fila en device_sessions
    close_reason: str | None = None  # fijado por quien cierra la sesión desde fuera

    def touch(self) -> None:
        self.last_seen = utcnow()

    async def send(self, data: bytes) -> None:
        self.writer.write(data)
        await self.writer.drain()

    def close(self, reason: str | None = None) -> None:
        if reason and self.close_reason is None:
            self.close_reason = reason
        if not self.writer.is_closing():
            self.writer.close()
