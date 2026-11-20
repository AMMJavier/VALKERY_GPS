"""Tipos comunes del protocolo: tramas, registros decodificados y errores.

Referencia Traccar: BaseFrameDecoder.java, BaseProtocolDecoder.java, BaseProtocolEncoder.java
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# --------------------------------------------------------------------- errores


class ProtocolError(ValueError):
    """Trama mal formada. La conexión debe cerrarse sin ACK."""


class CrcError(ProtocolError):
    """El CRC recibido no coincide con el calculado."""


class FrameTooLargeError(ProtocolError):
    """La trama declarada supera el límite configurado."""


class UnsupportedCodecError(ProtocolError):
    """Codec reconocible pero no soportado por esta plataforma."""


# --------------------------------------------------------------------- tramas


@dataclass(frozen=True, slots=True)
class ImeiFrame:
    imei: str


@dataclass(frozen=True, slots=True)
class DataFrame:
    """Trama completa con preámbulo de 4 ceros (AVL o Codec 12)."""

    raw: bytes


@dataclass(frozen=True, slots=True)
class PingFrame:
    """Byte 0xFF que el equipo envía para mantener viva la conexión."""


Frame = ImeiFrame | DataFrame | PingFrame


# --------------------------------------------------------------------- datos


IoValue = int | bytes


@dataclass(slots=True)
class AvlRecord:
    """Registro AVL tal como lo envía el equipo, sin interpretar.

    Los valores I/O se guardan como enteros sin signo (o bytes en la sección
    de longitud variable de Codec 8E). El signo y la escala dependen del ID y
    se aplican en ``io_elements.interpret``.
    """

    timestamp: datetime  # UTC, del GPS
    priority: int  # 0 low, 1 high, 2 panic
    longitude: float
    latitude: float
    altitude: int  # metros
    angle: int  # grados, 0 = norte
    satellites: int
    speed: int  # km/h
    event_io_id: int  # 0 si el registro no es por evento
    io: dict[int, IoValue] = field(default_factory=dict)


@dataclass(slots=True)
class AvlPacket:
    codec: int
    records: list[AvlRecord]


@dataclass(slots=True)
class CommandResponse:
    """Respuesta Codec 12 (tipo 0x06) a un comando enviado."""

    codec: int
    response_type: int
    payload: bytes

    @property
    def text(self) -> str:
        return self.payload.decode("ascii", errors="replace").strip()


DecodedMessage = AvlPacket | CommandResponse
