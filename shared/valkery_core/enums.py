"""Enums de dominio.

Los de eventos y comandos se agregan en sus fases (3 y 6).

Referencia Traccar: model/Event.java (TYPE_*), model/Command.java (TYPE_*)
"""

from __future__ import annotations

from enum import StrEnum


class Transport(StrEnum):
    TCP = "tcp"
    UDP = "udp"


class ParseStatus(StrEnum):
    OK = "ok"
    CRC_ERROR = "crc_error"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class CloseReason(StrEnum):
    DEVICE_CLOSED = "device_closed"
    IDLE_TIMEOUT = "idle_timeout"
    PROTOCOL_ERROR = "protocol_error"
    PROCESSING_ERROR = "processing_error"
    REPLACED = "replaced"
    SERVER_SHUTDOWN = "server_shutdown"
