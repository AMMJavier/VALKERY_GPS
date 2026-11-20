"""Decodificador de tramas de datos Teltonika.

Soporta:
- Codec 8 (0x08): IDs y contadores de I/O de 1 byte.
- Codec 8 Extended (0x8E): IDs y contadores de 2 bytes y una sección final
  de I/O de longitud variable (NX).
- Codec 12 (0x0C) tipo 0x06: respuesta del equipo a un comando.

Estructura de la trama (ver docs/protocol/teltonika-notas.md):
    00000000 | longitud (4B) | codec | N1 | registros... | N2 | CRC (4B)

Referencia Traccar: protocol/TeltonikaProtocolDecoder.java
"""

from __future__ import annotations

import logging
import struct
from datetime import UTC, datetime

from ..base import (
    AvlPacket,
    AvlRecord,
    CommandResponse,
    CrcError,
    DecodedMessage,
    IoValue,
    ProtocolError,
    UnsupportedCodecError,
)
from .crc import crc16_ibm

logger = logging.getLogger(__name__)

CODEC_8 = 0x08
CODEC_8_EXT = 0x8E
CODEC_12 = 0x0C

CODEC12_TYPE_COMMAND = 0x05
CODEC12_TYPE_RESPONSE = 0x06

COORDINATE_PRECISION = 10_000_000


class _Reader:
    """Lector secuencial big-endian con control de límites."""

    __slots__ = ("_data", "_pos")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    @property
    def remaining(self) -> int:
        return len(self._data) - self._pos

    def take(self, size: int) -> bytes:
        if size < 0 or self._pos + size > len(self._data):
            raise ProtocolError("trama truncada: faltan bytes")
        chunk = self._data[self._pos : self._pos + size]
        self._pos += size
        return chunk

    def uint(self, size: int) -> int:
        return int.from_bytes(self.take(size), "big")

    def int32(self) -> int:
        return struct.unpack(">i", self.take(4))[0]

    def int16(self) -> int:
        return struct.unpack(">h", self.take(2))[0]


def decode_data_frame(raw: bytes) -> DecodedMessage:
    """Valida cabecera, longitud y CRC, y decodifica el contenido."""
    if len(raw) < 15:
        raise ProtocolError("trama demasiado corta")
    if any(raw[0:4]):
        raise ProtocolError("preámbulo distinto de 4 ceros")

    data_length = int.from_bytes(raw[4:8], "big")
    if data_length + 12 != len(raw):
        raise ProtocolError(
            f"longitud declarada {data_length} no coincide con la trama ({len(raw) - 12})"
        )

    body = raw[8 : 8 + data_length]
    received_crc = int.from_bytes(raw[8 + data_length :], "big")
    calculated_crc = crc16_ibm(body)
    if received_crc != calculated_crc:
        raise CrcError(f"CRC recibido {received_crc:#06x}, calculado {calculated_crc:#06x}")

    codec = body[0]
    if codec in (CODEC_8, CODEC_8_EXT):
        return _decode_avl(body, codec)
    if codec == CODEC_12:
        return _decode_codec12(body)
    raise UnsupportedCodecError(f"codec no soportado: {codec:#04x}")


# --------------------------------------------------------------------- AVL


def _decode_avl(body: bytes, codec: int) -> AvlPacket:
    reader = _Reader(body)
    reader.uint(1)  # codec
    count = reader.uint(1)
    if count == 0:
        raise ProtocolError("paquete AVL sin registros")

    records = [_decode_record(reader, codec) for _ in range(count)]

    trailing_count = reader.uint(1)
    if trailing_count != count:
        raise ProtocolError(f"número de datos inconsistente: {count} != {trailing_count}")
    if reader.remaining:
        raise ProtocolError(f"{reader.remaining} bytes sobrantes tras los registros")
    return AvlPacket(codec=codec, records=records)


def _decode_record(reader: _Reader, codec: int) -> AvlRecord:
    timestamp_ms = reader.uint(8)
    priority = reader.uint(1)

    longitude = reader.int32() / COORDINATE_PRECISION
    latitude = reader.int32() / COORDINATE_PRECISION
    altitude = reader.int16()
    angle = reader.uint(2)
    satellites = reader.uint(1)
    speed = reader.uint(2)

    extended = codec == CODEC_8_EXT
    id_size = 2 if extended else 1

    event_io_id = reader.uint(id_size)
    total_io = reader.uint(id_size)

    io: dict[int, IoValue] = {}
    read_count = 0
    for value_size in (1, 2, 4, 8):
        group_count = reader.uint(id_size)
        read_count += group_count
        for _ in range(group_count):
            io_id = reader.uint(id_size)
            io[io_id] = reader.uint(value_size)

    if extended:
        group_count = reader.uint(2)
        read_count += group_count
        for _ in range(group_count):
            io_id = reader.uint(2)
            length = reader.uint(2)
            io[io_id] = reader.take(length)

    if total_io != read_count:
        # Algunos firmwares declaran un total distinto. El CRC ya garantiza la
        # integridad y la estructura se validó grupo a grupo: solo se advierte,
        # porque rechazar dejaría al equipo reintentando sin fin.
        logger.warning("total de I/O declarado %d, leídos %d", total_io, read_count)

    return AvlRecord(
        timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC),
        priority=priority,
        longitude=longitude,
        latitude=latitude,
        altitude=altitude,
        angle=angle,
        satellites=satellites,
        speed=speed,
        event_io_id=event_io_id,
        io=io,
    )


# --------------------------------------------------------------------- Codec 12


def _decode_codec12(body: bytes) -> CommandResponse:
    reader = _Reader(body)
    reader.uint(1)  # codec
    quantity = reader.uint(1)
    response_type = reader.uint(1)
    if response_type != CODEC12_TYPE_RESPONSE:
        raise UnsupportedCodecError(f"Codec 12 tipo {response_type:#04x} no soportado")
    size = reader.uint(4)
    payload = reader.take(size)
    trailing_quantity = reader.uint(1)
    if quantity != trailing_quantity:
        raise ProtocolError(f"cantidad Codec 12 inconsistente: {quantity} != {trailing_quantity}")
    if reader.remaining:
        raise ProtocolError("bytes sobrantes en Codec 12")
    return CommandResponse(codec=CODEC_12, response_type=response_type, payload=payload)
