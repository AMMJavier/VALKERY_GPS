"""Registro IMEI -> sesión activa. Es el único dueño de los sockets.

Si un equipo se reconecta mientras la sesión anterior sigue abierta (típico
tras perder cobertura), la sesión vieja se cierra y queda la nueva.

Referencia Traccar: session/ConnectionManager.java
"""

from __future__ import annotations

import logging

from valkery_core.enums import CloseReason

from .device_session import DeviceSession

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, DeviceSession] = {}

    def register(self, session: DeviceSession) -> None:
        previous = self._sessions.get(session.imei)
        if previous is not None and previous is not session:
            logger.info("IMEI %s reconectado desde %s; se cierra sesión previa", session.imei, session.peer)
            previous.close(CloseReason.REPLACED)
        self._sessions[session.imei] = session

    def unregister(self, session: DeviceSession) -> None:
        if self._sessions.get(session.imei) is session:
            del self._sessions[session.imei]

    def get(self, imei: str) -> DeviceSession | None:
        return self._sessions.get(imei)

    def is_online(self, imei: str) -> bool:
        return imei in self._sessions

    def all(self) -> list[DeviceSession]:
        return list(self._sessions.values())

    def __len__(self) -> int:
        return len(self._sessions)
