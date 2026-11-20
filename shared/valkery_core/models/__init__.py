"""Modelos de la base de datos. Alembic importa este módulo para conocer el esquema.

Las tablas de usuarios, eventos, geocercas, comandos y auditoría se agregan en
sus fases (3, 4 y 6) con su propia migración.
"""

from ..db.base import Base
from .device import Device
from .device_session import DeviceSessionRecord
from .device_state import DeviceState
from .position import Position
from .raw_packet import RawPacket
from .vehicle import Vehicle

__all__ = ["Base", "Device", "DeviceSessionRecord", "DeviceState", "Position", "RawPacket", "Vehicle"]
