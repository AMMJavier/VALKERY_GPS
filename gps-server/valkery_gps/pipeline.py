"""Contratos del pipeline de procesamiento.

El servidor entrega cada paquete decodificado a un ``RecordSink`` y solo envía
el ACK cuando ``handle_packet`` termina sin error (ADR 0003).

Implementaciones:
- ``handlers.database.DatabaseSink``: persistencia en MySQL (fase 2).
- ``LoggingSink``: solo registra en el log (pruebas y diagnóstico).

Referencia Traccar: ProcessingHandler.java, BasePipelineFactory.java
"""

from __future__ import annotations

import logging
from typing import Protocol

from .protocol.base import AvlPacket, CommandResponse, ProtocolError
from .protocol.teltonika.io_elements import interpret
from .session.device_session import DeviceSession

logger = logging.getLogger(__name__)


class DeviceRegistry(Protocol):
    async def authorize(self, imei: str) -> int | None:
        """Devuelve el device_id si el IMEI puede conectarse, o None."""
        ...


class RecordSink(Protocol):
    async def session_opened(self, session: DeviceSession) -> None: ...

    async def handle_packet(self, session: DeviceSession, packet: AvlPacket, raw: bytes) -> int:
        """Procesa el paquete y devuelve cuántos registros se aceptaron.

        Si lanza una excepción, no se envía ACK y el equipo reintentará.
        """
        ...

    async def handle_command_response(self, session: DeviceSession, response: CommandResponse, raw: bytes) -> None: ...

    async def packet_rejected(self, session: DeviceSession, raw: bytes, error: ProtocolError) -> None:
        """Trama completa que no se pudo decodificar (se guarda para diagnóstico)."""
        ...

    async def session_closed(self, session: DeviceSession, reason: str, device_still_online: bool) -> None: ...


class AllowListRegistry:
    """Autoriza IMEIs de una lista fija. Solo para pruebas y diagnóstico."""

    def __init__(self, imeis: frozenset[str] | set[str]) -> None:
        self._ids = {imei: i for i, imei in enumerate(sorted(imeis), start=1)}

    async def authorize(self, imei: str) -> int | None:
        return self._ids.get(imei)


class LoggingSink:
    async def session_opened(self, session: DeviceSession) -> None:
        pass

    async def handle_packet(self, session: DeviceSession, packet: AvlPacket, raw: bytes) -> int:
        for record in packet.records:
            logger.info(
                "IMEI %s | %s | lat=%.7f lon=%.7f vel=%d km/h ang=%d sat=%d evento=%d | %s",
                session.imei,
                record.timestamp.isoformat(),
                record.latitude,
                record.longitude,
                record.speed,
                record.angle,
                record.satellites,
                record.event_io_id,
                interpret(record.io),
            )
        return len(packet.records)

    async def handle_command_response(self, session: DeviceSession, response: CommandResponse, raw: bytes) -> None:
        logger.info("IMEI %s | respuesta Codec 12: %r", session.imei, response.text)

    async def packet_rejected(self, session: DeviceSession, raw: bytes, error: ProtocolError) -> None:
        pass

    async def session_closed(self, session: DeviceSession, reason: str, device_still_online: bool) -> None:
        pass
