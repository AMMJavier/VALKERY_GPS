"""Construye tramas AVL Codec 8 / 8E válidas.

Uso exclusivo para el simulador (tools/device_simulator.py) y las pruebas.
El servidor nunca genera tramas AVL.
"""

from __future__ import annotations

import struct

from ..base import AvlRecord
from .crc import crc16_ibm
from .decoder import CODEC_8, CODEC_8_EXT, COORDINATE_PRECISION


def build_avl_frame(records: list[AvlRecord], codec: int = CODEC_8) -> bytes:
    if codec not in (CODEC_8, CODEC_8_EXT):
        raise ValueError("codec no soportado por el builder")
    if not 1 <= len(records) <= 255:
        raise ValueError("entre 1 y 255 registros")

    body = bytes([codec, len(records)])
    body += b"".join(_build_record(r, codec) for r in records)
    body += bytes([len(records)])
    return b"\x00\x00\x00\x00" + len(body).to_bytes(4, "big") + body + crc16_ibm(body).to_bytes(4, "big")


def build_imei_frame(imei: str) -> bytes:
    raw = imei.encode("ascii")
    return len(raw).to_bytes(2, "big") + raw


def _build_record(record: AvlRecord, codec: int) -> bytes:
    extended = codec == CODEC_8_EXT
    id_size = 2 if extended else 1

    out = bytearray()
    out += int(record.timestamp.timestamp() * 1000).to_bytes(8, "big")
    out += record.priority.to_bytes(1, "big")
    out += struct.pack(
        ">iihHBH",
        round(record.longitude * COORDINATE_PRECISION),
        round(record.latitude * COORDINATE_PRECISION),
        record.altitude,
        record.angle,
        record.satellites,
        record.speed,
    )

    groups: dict[int, list[tuple[int, int]]] = {1: [], 2: [], 4: [], 8: []}
    variable: list[tuple[int, bytes]] = []
    for io_id, value in record.io.items():
        if isinstance(value, bytes):
            if not extended:
                raise ValueError("I/O de longitud variable solo en Codec 8E")
            variable.append((io_id, value))
        else:
            groups[_size_for(value)].append((io_id, value))

    out += record.event_io_id.to_bytes(id_size, "big")
    out += len(record.io).to_bytes(id_size, "big")
    for size, items in groups.items():
        out += len(items).to_bytes(id_size, "big")
        for io_id, value in items:
            out += io_id.to_bytes(id_size, "big") + value.to_bytes(size, "big")
    if extended:
        out += len(variable).to_bytes(2, "big")
        for io_id, value in variable:
            out += io_id.to_bytes(2, "big") + len(value).to_bytes(2, "big") + value
    return bytes(out)


def _size_for(value: int) -> int:
    for size in (1, 2, 4, 8):
        if 0 <= value < 1 << (size * 8):
            return size
    raise ValueError(f"valor I/O fuera de rango: {value}")


def _wrap(body: bytes) -> bytes:
    return b"\x00\x00\x00\x00" + len(body).to_bytes(4, "big") + body + crc16_ibm(body).to_bytes(4, "big")


def build_codec12_response(text: str) -> bytes:
    """Respuesta Codec 12 (tipo 0x06) como la enviaría el equipo."""
    content = text.encode("ascii")
    return _wrap(bytes([0x0C, 1, 0x06]) + len(content).to_bytes(4, "big") + content + b"\x01")


def parse_codec12_command(frame: bytes) -> str:
    """Extrae el texto de un comando Codec 12 (tipo 0x05) recibido del servidor."""
    if len(frame) < 17 or frame[:4] != b"\x00\x00\x00\x00":
        raise ValueError("trama Codec 12 inválida")
    length = int.from_bytes(frame[4:8], "big")
    body = frame[8 : 8 + length]
    if crc16_ibm(body) != int.from_bytes(frame[8 + length : 12 + length], "big"):
        raise ValueError("CRC inválido")
    if body[0] != 0x0C or body[2] != 0x05:
        raise ValueError("no es un comando Codec 12")
    size = int.from_bytes(body[3:7], "big")
    return body[7 : 7 + size].decode("ascii")
