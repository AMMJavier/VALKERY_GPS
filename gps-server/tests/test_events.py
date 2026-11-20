"""Detectores de eventos (sin base de datos)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from valkery_core.enums import EventType, GeofenceType, Severity
from valkery_core.geo import distance_to_polygon_edge_m, haversine_m, point_in_polygon, validate_polygon
from valkery_core.models import EventRule
from valkery_gps.handlers.events.alarm import detect_alarms
from valkery_gps.handlers.events.base import EventCandidate, PreviousState
from valkery_gps.handlers.events.engine import RuleBook
from valkery_gps.handlers.events.geofence import FenceShape, detect_geofences, is_inside
from valkery_gps.handlers.events.ignition import detect_ignition

T0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
GAP = timedelta(hours=1)
LAT, LON = 54.6990, 25.2618
M_LAT = 1 / 111_320  # grados por metro (latitud)


def row(i: int, *, ignition=None, valid=True, lat=LAT, lon=LON, event_io_id=0, io=None, t=None) -> dict:
    return {
        "id": 100 + i,
        "gps_time": t or T0 + timedelta(seconds=10 * i),
        "ignition": ignition,
        "valid": valid,
        "latitude": lat,
        "longitude": lon,
        "speed": 0,
        "event_io_id": event_io_id,
        "io": io or {},
    }


NO_STATE = PreviousState(ignition=None, last_gps_time=None, fix_time=None)


# --------------------------------------------------------------------- ignition


def types(events: list[EventCandidate]) -> list[EventType]:
    return [e.event_type for e in events]


def test_ignition_unknown_state_only_initializes():
    assert detect_ignition([row(0, ignition=True)], NO_STATE, GAP) == []


def test_ignition_transitions_in_batch():
    rows = [row(0, ignition=False), row(1, ignition=True), row(2, ignition=True), row(3, ignition=False)]
    events = detect_ignition(rows, NO_STATE, GAP)
    assert types(events) == [EventType.IGNITION_ON, EventType.IGNITION_OFF]
    assert events[0].position_id == 101 and events[0].occurred_at == T0 + timedelta(seconds=10)


def test_periodic_ignition_on_does_not_repeat():
    previous = PreviousState(ignition=True, last_gps_time=T0, fix_time=T0)
    rows = [row(i, ignition=True) for i in range(1, 20)]
    assert detect_ignition(rows, previous, GAP) == []


def test_transition_against_previous_state():
    previous = PreviousState(ignition=False, last_gps_time=T0, fix_time=T0)
    assert types(detect_ignition([row(1, ignition=True)], previous, GAP)) == [EventType.IGNITION_ON]


def test_change_after_long_gap_is_initial_state():
    previous = PreviousState(ignition=False, last_gps_time=T0, fix_time=T0)
    late = row(1, ignition=True, t=T0 + timedelta(hours=3))
    assert detect_ignition([late], previous, GAP) == []


def test_old_buffered_records_do_not_create_transitions():
    previous = PreviousState(ignition=False, last_gps_time=T0 + timedelta(minutes=10), fix_time=None)
    old = [row(0, ignition=True), row(1, ignition=False)]
    assert detect_ignition(old, previous, GAP) == []


def test_rows_out_of_order_in_packet_are_sorted():
    rows = [row(2, ignition=False), row(0, ignition=False), row(1, ignition=True)]
    assert types(detect_ignition(rows, NO_STATE, GAP)) == [EventType.IGNITION_ON, EventType.IGNITION_OFF]


def test_unknown_ignition_values_are_ignored():
    previous = PreviousState(ignition=False, last_gps_time=T0, fix_time=T0)
    assert detect_ignition([row(1, ignition=None)], previous, GAP) == []


# --------------------------------------------------------------------- alarmas


def test_alarm_only_when_record_caused_by_io():
    rows = [
        row(0, event_io_id=246, io={"246": 1}),  # remolque
        row(1, event_io_id=0, io={"246": 1}),  # periódico con el valor aún en 1
        row(2, event_io_id=246, io={"246": 0}),  # fin del remolque
        row(3, event_io_id=247, io={"247": 2}),  # choque
        row(4, event_io_id=249, io={"249": 1}),  # jamming
        row(5, event_io_id=252, io={"252": 1}),  # alimentación cortada
        row(6, event_io_id=239, io={"239": 1}),  # ignition no es alarma
    ]
    events = detect_alarms(rows)
    assert types(events) == [EventType.TOWING, EventType.CRASH, EventType.JAMMING, EventType.POWER_CUT]
    assert all(e.source.value == "device" for e in events)
    assert events[1].attributes["value"] == 2


# --------------------------------------------------------------------- geometría


def test_haversine_known_distance():
    assert haversine_m(LAT, LON, LAT + 100 * M_LAT, LON) == pytest.approx(100, rel=0.01)


def test_polygon_and_edge_distance():
    square = validate_polygon([[0, 0], [0, 0.01], [0.01, 0.01], [0.01, 0], [0, 0]])
    assert len(square) == 4  # el cierre repetido se elimina
    assert point_in_polygon(0.005, 0.005, square)
    assert not point_in_polygon(0.02, 0.005, square)
    assert distance_to_polygon_edge_m(0.011, 0.005, square) == pytest.approx(111, rel=0.02)


def test_invalid_polygon():
    with pytest.raises(ValueError):
        validate_polygon([[0, 0], [1, 1]])


# --------------------------------------------------------------------- geocercas

CIRCLE = FenceShape(1, "Casa", GeofenceType.CIRCLE, center=(LAT, LON), radius_m=100)


def at(meters_north: float) -> float:
    return LAT + meters_north * M_LAT


def test_circle_hysteresis():
    assert is_inside(CIRCLE, at(90), LON, None, 25)
    assert not is_inside(CIRCLE, at(110), LON, False, 25)  # para entrar hay que cruzar el radio
    assert is_inside(CIRCLE, at(110), LON, True, 25)  # dentro del margen: sigue dentro
    assert not is_inside(CIRCLE, at(130), LON, True, 25)


def test_geofence_initial_state_then_exit_and_enter():
    rows = [row(0, lat=at(0)), row(1, lat=at(300)), row(2, lat=at(10))]
    events, updates = detect_geofences(rows, [CIRCLE], {}, None, 25)
    assert types(events) == [EventType.GEOFENCE_EXIT, EventType.GEOFENCE_ENTER]
    assert events[0].geofence_id == 1 and events[0].attributes["geofence"] == "Casa"
    assert updates[1].inside is True and updates[1].position_id == 102


def test_geofence_jitter_at_border_does_not_flap():
    jitter = [95, 105, 98, 112, 101, 118, 99]
    rows = [row(i, lat=at(m)) for i, m in enumerate(jitter)]
    events, _ = detect_geofences(rows, [CIRCLE], {1: True}, None, 25)
    assert events == []


def test_geofence_ignores_invalid_and_old_positions():
    rows = [row(0, lat=at(500), valid=False), row(1, lat=at(500), t=T0 - timedelta(minutes=5))]
    events, updates = detect_geofences(rows, [CIRCLE], {1: True}, T0, 25)
    assert events == [] and updates == {}


def test_polygon_fence():
    d = 0.001
    poly = FenceShape(2, "Zona", GeofenceType.POLYGON, polygon=((LAT, LON), (LAT, LON + d), (LAT + d, LON + d), (LAT + d, LON)))
    rows = [row(0, lat=LAT + d / 2, lon=LON + d / 2), row(1, lat=LAT + 3 * d, lon=LON + d / 2)]
    events, _ = detect_geofences(rows, [poly], {}, None, 25)
    assert types(events) == [EventType.GEOFENCE_EXIT]


# --------------------------------------------------------------------- reglas


def test_rulebook_defaults_overrides_and_device_priority():
    rules = [
        EventRule(event_type="GEOFENCE_ENTER", device_id=None, enabled=False),
        EventRule(event_type="GEOFENCE_ENTER", device_id=7, enabled=True, severity="critical"),
        EventRule(event_type="IGNITION_ON", device_id=None, enabled=True, severity="warning"),
        EventRule(event_type="TOWING", device_id=8, enabled=False),
    ]
    book7 = RuleBook(rules, device_id=7)
    assert book7.severity_for(EventType.GEOFENCE_ENTER) == "critical"
    assert book7.severity_for(EventType.IGNITION_ON) == "warning"
    assert book7.severity_for(EventType.TOWING) == Severity.CRITICAL.value
    book9 = RuleBook(rules, device_id=9)
    assert book9.severity_for(EventType.GEOFENCE_ENTER) is None
    assert book9.severity_for(EventType.IGNITION_OFF) == Severity.INFO.value


def test_event_dedup_key():
    a = EventCandidate(EventType.IGNITION_ON, source=None, occurred_at=T0, position_id=5)  # type: ignore[arg-type]
    b = EventCandidate(EventType.IGNITION_OFF, source=None, occurred_at=T0, position_id=5)  # type: ignore[arg-type]
    c = EventCandidate(EventType.DEVICE_ONLINE, source=None, occurred_at=T0)  # type: ignore[arg-type]
    assert a.dedup_key() != b.dedup_key() and len(a.dedup_key()) == 32
    assert c.dedup_key() is None
