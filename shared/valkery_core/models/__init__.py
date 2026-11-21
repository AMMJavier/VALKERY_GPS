"""Modelos de la base de datos. Alembic importa este módulo para conocer el esquema.

Las tablas de comandos se agregan en la fase 6 con su propia migración.
"""

from ..db.base import Base
from .audit_log import AuditLog
from .device import Device
from .device_session import DeviceSessionRecord
from .device_state import DeviceState
from .event import Event, EventRule
from .geofence import DeviceGeofence, Geofence
from .position import Position
from .raw_packet import RawPacket
from .user import Role, RolePermission, User, UserRole
from .vehicle import Vehicle

__all__ = [
    "AuditLog",
    "Base",
    "Device",
    "DeviceGeofence",
    "DeviceSessionRecord",
    "DeviceState",
    "Event",
    "EventRule",
    "Geofence",
    "Position",
    "RawPacket",
    "Role",
    "RolePermission",
    "User",
    "UserRole",
    "Vehicle",
]
