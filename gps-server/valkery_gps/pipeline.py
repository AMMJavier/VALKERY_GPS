"""Contratos del pipeline de procesamiento.

El servidor entrega cada paquete decodificado a un ``RecordSink``, y solo
cuando ``handle_packet`` termina sin error envía el ACK al equipo (ADR 0003).

Fase 1: ``LoggingSink`` (registra en el log, no persiste).
Fase 2: un sink que encadena handlers (validity → distance → motion →
database) y luego los handlers de eventos.

Referencia Traccar: ProcessingHandler.java, BasePipelineFactory.java
"""

from __future__ import annotations

import logging
from typing import Protocol

from .protocol.base import AvlPacket, CommandResponse
from .protocol.teltonika.io_elements import interpret
from .session.device_session import DeviceSession

logger = logging.getLogger(__name__)


class RecordSink(Protocol):
    async def handle_packet(self, session: DeviceSession, packet: AvlPacket) -> int:
        """Procesa el paquete y devuelve cuántos registros se aceptaron.

        Si lanza una excepción, no se envía ACK y el equipo reintentará.
        """
        ...

    async def handle_command_response(self, session: DeviceSession, response: CommandResponse) -> None: ...


class DeviceAuthorizer(Protocol):
    async def is_authorized(self, imei: str) -> bool: ...


class AllowListAuthorizer:
    """Autoriza solo IMEIs configurados. En la fase 2 se reemplaza por la tabla devices."""

    def __init__(self, imeis: frozenset[str]) -> None:
        self._imeis = imeis

    async def is_authorized(self, imei: str) -> bool:
        return imei in self._imeis


class LoggingSink:
    async def handle_packet(self, session: DeviceSession, packet: AvlPacket) -> int:
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

    async def handle_command_response(self, session: DeviceSession, response: CommandResponse) -> None:
        logger.info("IMEI %s | respuesta Codec 12: %r", session.imei, response.text)
