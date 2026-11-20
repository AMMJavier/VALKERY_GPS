from datetime import UTC, datetime

from valkery_gps.handlers.normalize import dedup_key, io_to_json, position_row
from valkery_gps.handlers.validity import is_valid_position
from valkery_gps.protocol.base import AvlRecord
from valkery_gps.protocol.teltonika.decoder import decode_data_frame


def _record(**kw) -> AvlRecord:
    base = dict(
        timestamp=datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
        priority=0,
        longitude=25.2618832,
        latitude=54.6990336,
        altitude=148,
        angle=90,
        satellites=9,
        speed=30,
        event_io_id=0,
        io={239: 1, 240: 0, 179: 1, 69: 1, 66: 12850, 385: b"\x01\xab"},
    )
    base.update(kw)
    return AvlRecord(**base)


def test_valid_position():
    assert is_valid_position(_record())


def test_no_fix_when_zero_satellites():
    assert not is_valid_position(_record(satellites=0, speed=0, angle=0))


def test_no_fix_when_gnss_status_not_fix():
    assert not is_valid_position(_record(io={69: 2}))


def test_zero_coordinates_invalid():
    assert not is_valid_position(_record(latitude=0.0, longitude=0.0))


def test_pdf_example_valid(pdf_example):
    # 18 satélites y sin I/O 69 → válido
    assert is_valid_position(decode_data_frame(pdf_example).records[0])


def test_io_to_json_keeps_unknown_and_bytes():
    assert io_to_json({385: b"\x01\xab", 22: 1}) == {"22": 1, "385": "01ab"}


def test_dedup_key_stable_and_sensitive():
    assert dedup_key(_record()) == dedup_key(_record())
    assert dedup_key(_record()) != dedup_key(_record(speed=31))
    assert dedup_key(_record()) != dedup_key(_record(io={239: 0}))
    assert len(dedup_key(_record())) == 32


def test_position_row_first_level_fields():
    received = datetime(2026, 11, 20, 12, 0, 5, tzinfo=UTC)
    row = position_row(_record(), device_id=7, received_at=received, raw_packet_id=3)
    assert row["device_id"] == 7 and row["raw_packet_id"] == 3
    assert row["gps_time"] != row["received_at"]
    assert row["valid"] is True
    assert row["ignition"] is True and row["movement"] is False and row["dout1"] is True
    assert row["external_voltage_mv"] == 12850
    assert row["battery_voltage_mv"] is None
    assert row["course"] == 90
    assert row["io"]["385"] == "01ab"
