"""Motor de eventos contra MySQL (fase 3).

Criterio de aceptación: transiciones correctas y ausencia de falsas alarmas repetidas.
"""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from valkery_core.config import REPO_ROOT
from valkery_core.enums import GeofenceType
from valkery_core.models import Device, DeviceGeofence, DeviceState, Event, EventRule, Geofence
from valkery_gps.config import GpsServerConfig
from valkery_gps.handlers.database import DatabaseDeviceRegistry, DatabaseSink
from valkery_gps.protocol.base import AvlRecord
from valkery_gps.protocol.teltonika.avl_builder import build_avl_frame, build_imei_frame
from valkery_gps.protocol.teltonika.decoder import CODEC_8_EXT, decode_data_frame
from valkery_gps.schedule.inactivity import check_inactivity
from valkery_gps.server import GpsServer
from valkery_gps.session.device_session import DeviceSession

from ..conftest import TEST_IMEI

LAT, LON = 54.6990336, 25.2618832
T0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def _load_simulator():
    spec = importlib.util.spec_from_file_location("device_simulator", Path(REPO_ROOT) / "tools" / "device_simulator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeWriter:
    def is_closing(self) -> bool:
        return False

    def close(self) -> None:
        pass


def _session(device: Device) -> DeviceSession:
    return DeviceSession(imei=device.imei, device_id=device.id, peer="127.0.0.1:5000", writer=_FakeWriter())


def _rec(i: int, *, ignition: int, north_m: float = 0, event_io_id: int = 0, extra=None, t=None) -> AvlRecord:
    io = {239: ignition, 69: 1}
    io.update(extra or {})
    return AvlRecord(
        timestamp=t or T0 + timedelta(seconds=10 * i),
        priority=0,
        longitude=LON,
        latitude=round(LAT + north_m / 111_320, 7),
        altitude=20,
        angle=0,
        satellites=10,
        speed=30 if north_m else 0,
        event_io_id=event_io_id,
        io=io,
    )


async def _send(sink: DatabaseSink, session: DeviceSession, records: list[AvlRecord]) -> int:
    raw = build_avl_frame(records, CODEC_8_EXT)
    return await sink.handle_packet(session, decode_data_frame(raw), raw)


async def _events(factory) -> list[tuple[str, str]]:
    async with factory() as db:
        rows = (await db.scalars(select(Event).order_by(Event.occurred_at, Event.id))).all()
    return [(e.event_type, e.severity) for e in rows]


async def _add_circle(factory, radius_m: int = 150) -> int:
    async with factory.begin() as db:
        fence = Geofence(
            name="Casa", geofence_type=GeofenceType.CIRCLE.value, center_lat=LAT, center_lon=LON, radius_m=radius_m
        )
        db.add(fence)
        await db.flush()
        return fence.id


# --------------------------------------------------------------------- escenario completo


async def test_trip_scenario_events_in_order(session_factory, device):
    """El mismo recorrido que usa tools/device_simulator.py --scenario trip."""
    await _add_circle(session_factory)
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)

    trip = _load_simulator().make_trip(T0, LAT, LON)
    for i in range(0, len(trip), 4):
        await _send(sink, session, trip[i : i + 4])

    assert [t for t, _ in await _events(session_factory)] == [
        "IGNITION_ON",
        "GEOFENCE_EXIT",
        "IGNITION_OFF",
        "TOWING",
    ]
    async with session_factory() as db:
        towing = await db.scalar(select(Event).where(Event.event_type == "TOWING"))
        exit_event = await db.scalar(select(Event).where(Event.event_type == "GEOFENCE_EXIT"))
        fence_state = await db.scalar(select(DeviceGeofence))
    assert towing.severity == "critical" and towing.source == "device" and towing.position_id is not None
    assert exit_event.geofence_id is not None and exit_event.attributes["geofence"] == "Casa"
    assert fence_state.inside is False


async def test_retransmission_does_not_repeat_events(session_factory, device):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)
    packet = [_rec(0, ignition=0), _rec(1, ignition=1), _rec(2, ignition=0, event_io_id=247, extra={247: 1})]

    await _send(sink, session, packet)
    first = await _events(session_factory)
    await _send(sink, session, packet)  # el equipo no recibió el ACK y reenvía
    assert await _events(session_factory) == first
    assert [t for t, _ in first] == ["IGNITION_ON", "IGNITION_OFF", "CRASH"]


async def test_periodic_ignition_on_records_produce_single_event(session_factory, device):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)
    await _send(sink, session, [_rec(0, ignition=0)])
    for i in range(1, 30, 3):
        await _send(sink, session, [_rec(i, ignition=1), _rec(i + 1, ignition=1), _rec(i + 2, ignition=1)])
    assert [t for t, _ in await _events(session_factory)] == ["IGNITION_ON"]


async def test_old_buffered_records_after_newer_state(session_factory, device):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)
    await _send(sink, session, [_rec(100, ignition=0)])
    # Llegan tarde registros viejos de la memoria del equipo: con un remolque real.
    await _send(sink, session, [_rec(1, ignition=1), _rec(2, ignition=0, event_io_id=246, extra={246: 1})])
    assert [t for t, _ in await _events(session_factory)] == ["TOWING"]
    async with session_factory() as db:
        assert (await db.get(DeviceState, device.id)).ignition is False


# --------------------------------------------------------------------- reglas


async def test_rules_disable_and_change_severity(session_factory, device):
    async with session_factory.begin() as db:
        db.add(EventRule(event_type="IGNITION_ON", device_id=None, enabled=False))
        db.add(EventRule(event_type="IGNITION_OFF", device_id=device.id, enabled=True, severity="warning"))
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)
    await _send(sink, session, [_rec(0, ignition=0), _rec(1, ignition=1), _rec(2, ignition=0)])
    assert await _events(session_factory) == [("IGNITION_OFF", "warning")]


# --------------------------------------------------------------------- conectividad


async def test_offline_reported_once_then_online(session_factory, device):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)

    future = datetime.now(UTC) + timedelta(hours=2)
    assert await check_inactivity(session_factory, offline_after_s=1800, now=future) == 1
    assert await check_inactivity(session_factory, offline_after_s=1800, now=future) == 0  # no se repite

    await _send(sink, session, [_rec(0, ignition=0)])
    await _send(sink, session, [_rec(1, ignition=0)])
    async with session_factory() as db:
        # Orden de inserción: la verificación usó una hora "futura" simulada.
        in_order = (await db.scalars(select(Event.event_type).order_by(Event.id))).all()
    assert in_order == ["DEVICE_OFFLINE", "DEVICE_ONLINE"]
    async with session_factory() as db:
        state = await db.get(DeviceState, device.id)
        offline = await db.scalar(select(Event).where(Event.event_type == "DEVICE_OFFLINE"))
    assert state.reported_offline is False
    assert offline.position_id is None and "last_seen" in offline.attributes


async def test_recent_device_is_not_offline(session_factory, device):
    sink = DatabaseSink(session_factory)
    await sink.session_opened(_session(device))
    assert await check_inactivity(session_factory, offline_after_s=1800) == 0
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Event)) == 0


# --------------------------------------------------------------------- de punta a punta


async def test_end_to_end_trip_through_tcp(session_factory, device):
    await _add_circle(session_factory)
    sink = DatabaseSink(session_factory)
    cfg = GpsServerConfig(host="127.0.0.1", port=0, handshake_timeout_s=2, idle_timeout_s=2)
    server = GpsServer(cfg, DatabaseDeviceRegistry(session_factory), sink)
    await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(build_imei_frame(TEST_IMEI))
        await writer.drain()
        assert await reader.readexactly(1) == b"\x01"
        trip = _load_simulator().make_trip(T0, LAT, LON)
        for i in range(0, len(trip), 5):
            chunk = trip[i : i + 5]
            writer.write(build_avl_frame(chunk, CODEC_8_EXT))
            await writer.drain()
            assert int.from_bytes(await asyncio.wait_for(reader.readexactly(4), 5), "big") == len(chunk)
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.2)
    finally:
        await server.stop()
    assert [t for t, _ in await _events(session_factory)] == ["IGNITION_ON", "GEOFENCE_EXIT", "IGNITION_OFF", "TOWING"]
