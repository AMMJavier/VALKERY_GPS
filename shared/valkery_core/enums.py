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


class EventType(StrEnum):
    # Transiciones de estado
    IGNITION_ON = "IGNITION_ON"
    IGNITION_OFF = "IGNITION_OFF"
    # Alarmas nativas del equipo (I/O eventuales)
    TOWING = "TOWING"
    CRASH = "CRASH"
    JAMMING = "JAMMING"
    POWER_CUT = "POWER_CUT"
    # Reglas de plataforma
    GEOFENCE_ENTER = "GEOFENCE_ENTER"
    GEOFENCE_EXIT = "GEOFENCE_EXIT"
    # Conectividad (última comunicación, no ignition)
    DEVICE_ONLINE = "DEVICE_ONLINE"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class EventSource(StrEnum):
    DEVICE = "device"  # alarma generada por el equipo
    PLATFORM = "platform"  # deducida por la plataforma


DEFAULT_SEVERITY: dict[EventType, Severity] = {
    EventType.IGNITION_ON: Severity.INFO,
    EventType.IGNITION_OFF: Severity.INFO,
    EventType.TOWING: Severity.CRITICAL,
    EventType.CRASH: Severity.CRITICAL,
    EventType.JAMMING: Severity.CRITICAL,
    EventType.POWER_CUT: Severity.CRITICAL,
    EventType.GEOFENCE_ENTER: Severity.INFO,
    EventType.GEOFENCE_EXIT: Severity.WARNING,
    EventType.DEVICE_ONLINE: Severity.INFO,
    EventType.DEVICE_OFFLINE: Severity.WARNING,
}


class GeofenceType(StrEnum):
    CIRCLE = "circle"
    POLYGON = "polygon"
