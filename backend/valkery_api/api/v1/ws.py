"""WebSocket de estado en vivo (ADR 0002).

Conexión:  ws://host/api/v1/ws?token=<JWT>   (requiere positions:read)

El navegador no puede enviar cabeceras en un WebSocket, por eso el token va
en la URL; en producción debe usarse wss:// (TLS) para no exponerlo.

Mensajes del servidor (JSON):
    {"type": "snapshot", "devices": [DeviceOut...], "events": [EventOut...]}   al conectar
    {"type": "state", "device": DeviceOut}                                     cuando cambia un estado
    {"type": "event", "event": EventOut}                                       cada evento nuevo

La API consulta device_states y events cada VALKERY_API_WS_POLL_S segundos;
para un vehículo es suficiente y no requiere infraestructura adicional.
Cierra con código 4401 si el token expira o el usuario deja de ser válido.

Referencia Traccar: api/AsyncSocket.java
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from valkery_core.enums import Permission
from valkery_core.models import Device, DeviceState, Event, User

from ...core.deps import authenticate_token
from ...core.security import InvalidToken, decode_access_token
from ...schemas import DeviceOut, DeviceStateOut, EventOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["live"])

SNAPSHOT_EVENTS = 20
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403


async def _devices(db) -> dict[int, dict]:
    rows = (
        await db.execute(
            select(Device, DeviceState).outerjoin(DeviceState, DeviceState.device_id == Device.id).order_by(Device.id)
        )
    ).all()
    result = {}
    for device, state in rows:
        out = DeviceOut.model_validate(device)
        out.state = DeviceStateOut.model_validate(state) if state else None
        result[device.id] = out.model_dump(mode="json")
    return result


@router.websocket("/ws")
async def live(websocket: WebSocket, token: str = "") -> None:
    app = websocket.app
    settings = app.state.settings
    factory = app.state.session_factory

    try:
        user_id, version, expires = decode_access_token(token, settings)
        async with factory() as db:
            current = await authenticate_token(db, token, settings)
    except (InvalidToken, HTTPException):
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    if not current.has(Permission.POSITIONS_READ):
        await websocket.close(code=CLOSE_FORBIDDEN)
        return

    await websocket.accept()
    try:
        async with factory() as db:
            devices = await _devices(db)
            recent = (
                await db.scalars(select(Event).order_by(Event.id.desc()).limit(SNAPSHOT_EVENTS))
            ).all()
            last_event_id = await db.scalar(select(func.coalesce(func.max(Event.id), 0)))
        await websocket.send_json(
            {
                "type": "snapshot",
                "devices": list(devices.values()),
                "events": [EventOut.model_validate(e).model_dump(mode="json") for e in reversed(recent)],
            }
        )

        receiver = asyncio.create_task(_drain(websocket))
        try:
            while not receiver.done():
                await asyncio.sleep(settings.ws_poll_s)
                if datetime.now(UTC) >= expires:
                    await websocket.close(code=CLOSE_UNAUTHORIZED)
                    return
                async with factory() as db:
                    user = await db.get(User, user_id)
                    if user is None or not user.enabled or user.token_version != version:
                        await websocket.close(code=CLOSE_UNAUTHORIZED)
                        return
                    current_devices = await _devices(db)
                    new_events = (
                        await db.scalars(select(Event).where(Event.id > last_event_id).order_by(Event.id))
                    ).all()
                for device_id, data in current_devices.items():
                    if devices.get(device_id) != data:
                        await websocket.send_json({"type": "state", "device": data})
                devices = current_devices
                for event in new_events:
                    await websocket.send_json(
                        {"type": "event", "event": EventOut.model_validate(event).model_dump(mode="json")}
                    )
                    last_event_id = event.id
        finally:
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await receiver
    except WebSocketDisconnect:
        pass


async def _drain(websocket: WebSocket) -> None:
    """Consume (y descarta) mensajes del cliente para detectar la desconexión."""
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        while True:
            await websocket.receive_text()
