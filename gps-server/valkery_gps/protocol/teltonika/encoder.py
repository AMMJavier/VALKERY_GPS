"""Mensajes del servidor hacia el equipo Teltonika.

- Respuesta al IMEI: 1 byte (0x01 acepta, 0x00 rechaza).
- ACK de datos: entero de 4 bytes con la cantidad de registros aceptados.
- Comando Codec 12 (tipo 0x05):
    00000000 | len (4B) | 0C | 01 | 05 | cmdLen (4B) | comando | 01 | CRC (4B)

Los comandos de inmovilización NO se envían desde aquí directamente: el envío
pasa por commands/dispatcher.py (fase 6) con sus validaciones.

Referencia Traccar: protocol/TeltonikaProtocolEncoder.java
"""

from __future__ import annotations

from .crc import crc16_ibm
from .decoder import CODEC12_TYPE_COMMAND, CODEC_12

IMEI_ACCEPTED = b"\x01"
IMEI_REJECTED = b"\x00"

MAX_COMMAND_BYTES = 512


def encode_imei_response(accepted: bool) -> bytes:
    return IMEI_ACCEPTED if accepted else IMEI_REJECTED


def encode_records_ack(count: int) -> bytes:
    if not 0 <= count <= 255:
        raise ValueError("cantidad de registros fuera de rango")
    return count.to_bytes(4, "big")


def encode_codec12_command(command: str | bytes) -> bytes:
    content = command.encode("ascii") if isinstance(command, str) else bytes(command)
    if not content or len(content) > MAX_COMMAND_BYTES:
        raise ValueError("comando vacío o demasiado largo")

    body = (
        bytes([CODEC_12, 1, CODEC12_TYPE_COMMAND])
        + len(content).to_bytes(4, "big")
        + content
        + b"\x01"
    )
    return (
        b"\x00\x00\x00\x00"
        + len(body).to_bytes(4, "big")
        + body
        + crc16_ibm(body).to_bytes(4, "big")
    )
