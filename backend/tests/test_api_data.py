"""Dispositivos, posiciones, eventos, geocercas, reglas, auditoría y separación de roles."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from valkery_core.models import DeviceState, Event, Position

API = "/api/v1"
T0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


async def _positions(session_factory, device_id: int, count: int) -> None:
    async with session_factory.begin() as db:
        for i in range(count):
            db.add(
                Position(
                    device_id=device_id,
                    gps_time=T0 + timedelta(seconds=10 * i),
                    received_at=T0 + timedelta(seconds=10 * i + 2),
                    valid=i % 5 != 0,
                    latitude=54.69 + i / 10000,
                    longitude=25.26,
                    altitude=10,
                    speed=30,
                    course=0,
                    satellites=9,
                    priority=0,
                    event_io_id=0,
                    ignition=True,
                    io={"239": 1, "385": "01ab"},
                    dedup_key=hashlib.sha256(f"p{i}".encode()).digest(),
                )
            )


async def _events(session_factory, device_id: int, count: int) -> None:
    async with session_factory.begin() as db:
        for i in range(count):
            db.add(
                Event(
                    device_id=device_id,
                    event_type="IGNITION_ON" if i % 2 else "TOWING",
                    severity="info" if i % 2 else "critical",
                    source="platform" if i % 2 else "device",
                    occurred_at=T0 + timedelta(minutes=i),
                    created_at=T0 + timedelta(minutes=i),
                    attributes={},
                )
            )


# --------------------------------------------------------------------- separación de roles


@pytest.mark.parametrize(
    ("role", "method", "path", "body", "allowed"),
    [
        ("viewer", "GET", "/devices", None, True),
        ("viewer", "GET", "/events", None, True),
        ("viewer", "POST", "/geofences", {"name": "z", "geofence_type": "circle", "center_lat": 1, "center_lon": 1, "radius_m": 50}, False),
        ("viewer", "PUT", "/event-rules", {"event_type": "TOWING", "enabled": False}, False),
        ("viewer", "GET", "/users", None, False),
        ("viewer", "GET", "/audit", None, False),
        ("viewer", "POST", "/devices", {"imei": "123456789012345", "name": "x"}, False),
        ("operator", "POST", "/geofences", {"name": "z", "geofence_type": "circle", "center_lat": 1, "center_lon": 1, "radius_m": 50}, True),
        ("operator", "PUT", "/event-rules", {"event_type": "TOWING", "enabled": False}, True),
        ("operator", "POST", "/devices", {"imei": "123456789012345", "name": "x"}, False),
        ("operator", "GET", "/users", None, False),
        ("admin", "POST", "/devices", {"imei": "123456789012345", "name": "x"}, True),
        ("admin", "GET", "/audit", None, True),
    ],
)
async def test_role_separation(client, make_user, role, method, path, body, allowed):
    _, headers = await make_user(f"u_{role}", (role,))
    response = await client.request(method, f"{API}{path}", headers=headers, json=body)
    if allowed:
        assert response.status_code in (200, 201), response.text
    else:
        assert response.status_code == 403, response.text


# --------------------------------------------------------------------- dispositivos


async def test_devices_with_state_and_validation(client, make_user, device, session_factory):
    async with session_factory.begin() as db:
        db.add(DeviceState(device_id=device.id, online=True, ignition=True, latitude=54.7, longitude=25.3))
    _, admin = await make_user()

    devices = (await client.get(f"{API}/devices", headers=admin)).json()
    assert devices[0]["imei"] == device.imei
    assert devices[0]["state"]["online"] is True and devices[0]["state"]["latitude"] == 54.7

    assert (await client.post(f"{API}/devices", headers=admin, json={"imei": "12AB", "name": "x"})).status_code == 422
    dup = await client.post(f"{API}/devices", headers=admin, json={"imei": device.imei, "name": "x"})
    assert dup.status_code == 409
    assert (await client.get(f"{API}/devices/999", headers=admin)).status_code == 404

    vehicle = await client.post(f"{API}/vehicles", headers=admin, json={"alias": "Mi moto"})
    patched = await client.patch(
        f"{API}/devices/{device.id}", headers=admin, json={"name": "FMC920", "vehicle_id": vehicle.json()["id"]}
    )
    assert patched.status_code == 200 and patched.json()["vehicle_id"] == vehicle.json()["id"]
    bad_vehicle = await client.patch(f"{API}/devices/{device.id}", headers=admin, json={"vehicle_id": 999})
    assert bad_vehicle.status_code == 422


# --------------------------------------------------------------------- posiciones


async def test_positions_pagination_no_gaps_no_repeats(client, make_user, device, session_factory):
    await _positions(session_factory, device.id, 25)
    _, headers = await make_user("ana", ("viewer",))
    params = {"from": T0.isoformat(), "to": (T0 + timedelta(hours=1)).isoformat(), "limit": 10}

    seen, cursor, pages = [], None, 0
    while True:
        response = await client.get(
            f"{API}/devices/{device.id}/positions", headers=headers, params={**params, **({"cursor": cursor} if cursor else {})}
        )
        assert response.status_code == 200, response.text
        page = response.json()
        seen += [p["gps_time"] for p in page["items"]]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages == 3 and len(seen) == 25 and len(set(seen)) == 25 and seen == sorted(seen)
    assert page["items"][0]["io"] is None  # el mapa I/O solo con include_io=true


async def test_positions_filters_and_validation(client, make_user, device, session_factory):
    await _positions(session_factory, device.id, 25)
    _, headers = await make_user("ana", ("viewer",))
    url = f"{API}/devices/{device.id}/positions"
    base = {"from": T0.isoformat(), "to": (T0 + timedelta(hours=1)).isoformat()}

    valid = (await client.get(url, headers=headers, params={**base, "valid_only": True, "include_io": True})).json()
    assert len(valid["items"]) == 20 and valid["items"][0]["io"]["385"] == "01ab"

    window = {"from": (T0 + timedelta(seconds=50)).isoformat(), "to": (T0 + timedelta(seconds=100)).isoformat()}
    assert len((await client.get(url, headers=headers, params=window)).json()["items"]) == 5  # [from, to)

    reversed_range = {"from": base["to"], "to": base["from"]}
    assert (await client.get(url, headers=headers, params=reversed_range)).status_code == 422
    too_long = {"from": T0.isoformat(), "to": (T0 + timedelta(days=40)).isoformat()}
    assert (await client.get(url, headers=headers, params=too_long)).status_code == 422
    naive = {"from": "2026-11-20T12:00:00", "to": "2026-11-20T13:00:00"}
    assert (await client.get(url, headers=headers, params=naive)).status_code == 422
    assert (await client.get(url, headers=headers, params={**base, "cursor": "basura"})).status_code == 422
    assert (await client.get(f"{API}/devices/999/positions", headers=headers, params=base)).status_code == 404


# --------------------------------------------------------------------- eventos


async def test_events_filters_and_pagination(client, make_user, device, session_factory):
    await _events(session_factory, device.id, 9)
    _, headers = await make_user("ana", ("viewer",))

    first = (await client.get(f"{API}/events", headers=headers, params={"limit": 4})).json()
    assert len(first["items"]) == 4 and first["next_cursor"]
    times = [e["occurred_at"] for e in first["items"]]
    assert times == sorted(times, reverse=True)  # más recientes primero
    second = (await client.get(f"{API}/events", headers=headers, params={"limit": 4, "cursor": first["next_cursor"]})).json()
    assert not {e["id"] for e in first["items"]} & {e["id"] for e in second["items"]}

    towing = (await client.get(f"{API}/events", headers=headers, params={"event_type": "TOWING"})).json()
    assert len(towing["items"]) == 5 and {e["severity"] for e in towing["items"]} == {"critical"}
    critical = (await client.get(f"{API}/events", headers=headers, params={"severity": "critical"})).json()
    assert len(critical["items"]) == 5
    assert (await client.get(f"{API}/events", headers=headers, params={"event_type": "NO_EXISTE"})).status_code == 422


# --------------------------------------------------------------------- geocercas y reglas


async def test_geofence_crud_and_validation(client, make_user):
    _, op = await make_user("op", ("operator",))
    circle = await client.post(
        f"{API}/geofences",
        headers=op,
        json={"name": "Casa", "geofence_type": "circle", "center_lat": 54.69, "center_lon": 25.26, "radius_m": 150},
    )
    assert circle.status_code == 201 and circle.json()["points"] is None
    polygon = await client.post(
        f"{API}/geofences",
        headers=op,
        json={"name": "Zona", "geofence_type": "polygon", "points": [[0, 0], [0, 1], [1, 1], [0, 0]]},
    )
    assert polygon.status_code == 201 and len(polygon.json()["points"]) == 3

    bad = [
        {"name": "x", "geofence_type": "circle", "center_lat": 54.69},
        {"name": "x", "geofence_type": "polygon", "points": [[0, 0], [1, 1]]},
        {"name": "x", "geofence_type": "polygon", "points": [[0, 0, 0], [1, 1], [2, 2]]},
        {"name": "x", "geofence_type": "circle", "center_lat": 95, "center_lon": 0, "radius_m": 10},
    ]
    for body in bad:
        assert (await client.post(f"{API}/geofences", headers=op, json=body)).status_code == 422, body

    fence_id = circle.json()["id"]
    updated = await client.put(
        f"{API}/geofences/{fence_id}",
        headers=op,
        json={"name": "Casa 2", "geofence_type": "circle", "center_lat": 54.7, "center_lon": 25.3, "radius_m": 200, "enabled": False},
    )
    assert updated.json()["radius_m"] == 200 and updated.json()["enabled"] is False
    assert (await client.delete(f"{API}/geofences/{fence_id}", headers=op)).status_code == 204
    assert len((await client.get(f"{API}/geofences", headers=op)).json()) == 1


async def test_event_rules_upsert(client, make_user, device):
    _, op = await make_user("op", ("operator",))
    first = await client.put(f"{API}/event-rules", headers=op, json={"event_type": "GEOFENCE_ENTER", "enabled": False})
    again = await client.put(
        f"{API}/event-rules", headers=op, json={"event_type": "GEOFENCE_ENTER", "enabled": True, "severity": "warning"}
    )
    assert first.json()["id"] == again.json()["id"]  # misma regla, reemplazada
    per_device = await client.put(
        f"{API}/event-rules", headers=op, json={"event_type": "GEOFENCE_ENTER", "device_id": device.id, "enabled": False}
    )
    assert per_device.json()["id"] != first.json()["id"]
    rules = (await client.get(f"{API}/event-rules", headers=op)).json()
    assert len(rules) == 2
    bad = await client.put(f"{API}/event-rules", headers=op, json={"event_type": "TOWING", "severity": "urgente"})
    assert bad.status_code == 422


async def test_audit_listing(client, make_user):
    _, admin = await make_user()
    await client.post(f"{API}/vehicles", headers=admin, json={"alias": "Moto"})
    entries = (await client.get(f"{API}/audit", headers=admin)).json()["items"]
    assert [e["action"] for e in entries][:2] == ["vehicle_created", "login"]


async def test_health(client):
    assert (await client.get("/health")).json() == {"status": "ok", "database": "ok"}
