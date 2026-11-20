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
    peer: str
    writer: asyncio.StreamWriter = field(repr=False)
    connected_at: datetime = field(default_factory=utcnow)
    last_seen: datetime = field(default_factory=utcnow)
    packets_received: int = 0
    records_received: int = 0

    def touch(self) -> None:
        self.last_seen = utcnow()

    async def send(self, data: bytes) -> None:
        self.writer.write(data)
        await self.writer.drain()

    def close(self) -> None:
        if not self.writer.is_closing():
            self.writer.close()
