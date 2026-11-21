"""WebSocket de estado en vivo.

Usa el TestClient (síncrono) de Starlette, que ejecuta la app en su propio
bucle de eventos: la app crea su motor de base de datos en el lifespan, y los
datos de prueba se preparan con asyncio.run en otro motor.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from conftest import PASSWORD, TEST_IMEI, api_settings
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from valkery_api.main import create_app
from valkery_api.services.users import create_user
from valkery_core.db import create_engine, create_session_factory
from valkery_core.models import Device, DeviceState, Event
from valkery_core.testing import truncate_all


async def _run(db_url: str, coro_factory):
    engine = create_engine(db_url)
    try:
        return await coro_factory(create_session_factory(engine), engine)
    finally:
        await engine.dispose()


async def _setup(factory, engine):
    await truncate_all(engine)
    async with factory.begin() as db:
        await create_user(db, username="ana", password=PASSWORD, roles=["viewer"])
        await create_user(db, username="sinpermiso", password=PASSWORD, roles=["viewer"])
        device = Device(imei=TEST_IMEI, name="Moto", enabled=True)
        db.add(device)
        await db.flush()
        db.add(DeviceState(device_id=device.id, online=False))
    return device.id


def _event(device_id: int):
    async def insert(factory, _engine):
        async with factory.begin() as db:
            now = datetime.now(UTC)
            db.add(
                Event(
                    device_id=device_id,
                    event_type="TOWING",
                    severity="critical",
                    source="device",
                    occurred_at=now,
                    created_at=now,
                    attributes={"value": 1},
                )
            )
            state = await db.get(DeviceState, device_id)
            state.online = True

    return insert


def _token(client: TestClient, username: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_websocket_snapshot_then_live_updates(db_url):
    device_id = asyncio.run(_run(db_url, _setup))
    app = create_app(api_settings(ws_poll_s=0.1), db_url=db_url)
    with TestClient(app) as client:
        token = _token(client, "ana")
        with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
            snapshot = ws.receive_json()
            assert snapshot["type"] == "snapshot"
            assert snapshot["devices"][0]["state"]["online"] is False
            assert snapshot["events"] == []

            asyncio.run(_run(db_url, _event(device_id)))
            messages = [ws.receive_json(), ws.receive_json()]
            by_type = {m["type"]: m for m in messages}
            assert by_type["state"]["device"]["state"]["online"] is True
            assert by_type["event"]["event"]["event_type"] == "TOWING"


def test_websocket_rejects_missing_or_bad_token(db_url):
    asyncio.run(_run(db_url, _setup))
    app = create_app(api_settings(), db_url=db_url)
    with TestClient(app) as client:
        for url in ("/api/v1/ws", "/api/v1/ws?token=malo"):
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(url) as ws:
                    ws.receive_json()
            assert exc.value.code == 4401
