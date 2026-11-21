"""Precondiciones e interpretación de respuestas (sin base de datos)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from valkery_core.commands import SPECS, CommandType, analyze_response, check_preconditions, failed
from valkery_core.config import CoreSettings
from valkery_gps.protocol.teltonika.avl_builder import build_codec12_response, parse_codec12_command
from valkery_gps.protocol.teltonika.decoder import decode_data_frame
from valkery_gps.protocol.teltonika.encoder import encode_codec12_command

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
ON = CoreSettings(_env_file=None, commands_enabled=True, commands_relay_enabled=True)


def parked(**kw):
    base = dict(
        last_seen=NOW - timedelta(seconds=10),
        last_gps_time=NOW - timedelta(seconds=15),
        ignition=False,
        speed=0,
        movement=False,
        dout1=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def names(checks):
    return {c.name for c in failed(checks)}


def immobilize(state, settings=ON, online=True, enabled=True):
    return check_preconditions(
        SPECS[CommandType.IMMOBILIZE], settings=settings, device_enabled=enabled, online=online, state=state, now=NOW
    )


def test_parked_motorcycle_passes():
    assert names(immobilize(parked())) == set()


@pytest.mark.parametrize(
    ("state_change", "expected"),
    [
        ({"ignition": True}, "ignition_off"),
        ({"ignition": None}, "ignition_off"),  # desconocido NO es seguro
        ({"speed": 5}, "speed_zero"),
        ({"speed": None}, "speed_zero"),
        ({"movement": True}, "not_moving"),
        ({"movement": None}, "not_moving"),
        ({"last_seen": NOW - timedelta(minutes=10)}, "recent_communication"),
        ({"last_gps_time": NOW - timedelta(minutes=10)}, "recent_record"),
        ({"last_gps_time": None}, "recent_record"),
        ({"dout1": True}, "not_already_active"),
    ],
)
def test_each_unsafe_condition_blocks(state_change, expected):
    assert expected in names(immobilize(parked(**state_change)))


def test_speed_zero_alone_is_not_enough():
    """El documento prohíbe confiar solo en la velocidad GPS."""
    problems = names(immobilize(parked(ignition=True, movement=True)))
    assert {"ignition_off", "not_moving"} <= problems


def test_switches_offline_and_disabled_device():
    off = CoreSettings(_env_file=None, commands_enabled=False, commands_relay_enabled=False)
    assert {"commands_enabled", "relay_enabled"} <= names(immobilize(parked(), settings=off))
    assert "online" in names(immobilize(parked(), online=False))
    assert "device_enabled" in names(immobilize(parked(), enabled=False))


def test_release_does_not_require_stopped_motorcycle():
    checks = check_preconditions(
        SPECS[CommandType.RELEASE], settings=ON, device_enabled=True, online=True, state=parked(ignition=True, speed=40), now=NOW
    )
    assert names(checks) == set()


def test_diagnostics_do_not_need_relay_switch():
    only_commands = CoreSettings(_env_file=None, commands_enabled=True, commands_relay_enabled=False)
    checks = check_preconditions(
        SPECS[CommandType.GET_VERSION], settings=only_commands, device_enabled=True, online=True, state=None, now=NOW
    )
    assert names(checks) == set()


def test_permissions_and_texts():
    assert "commands:immobilize" in {p.value for p in SPECS[CommandType.IMMOBILIZE].permissions}
    assert "commands:immobilize" not in {p.value for p in SPECS[CommandType.RELEASE].permissions}
    assert SPECS[CommandType.IMMOBILIZE].text(ON) == "setdigout 1"
    custom = CoreSettings(_env_file=None, command_immobilize_text="setdigout 1 0 10")
    assert SPECS[CommandType.IMMOBILIZE].text(custom) == "setdigout 1 0 10"


@pytest.mark.parametrize(
    ("command", "text", "ok", "dout1"),
    [
        (CommandType.IMMOBILIZE, "DOUT1:1 Timeout:INFINITY", True, True),
        (CommandType.IMMOBILIZE, "DOUT1:0 Timeout:INFINITY", False, False),
        (CommandType.RELEASE, "DOUT1:0 Timeout:INFINITY", True, False),
        (CommandType.IMMOBILIZE, "OK", True, None),  # sin DOUT1: queda para verificar
        (CommandType.IMMOBILIZE, "Unknown command", False, None),
        (CommandType.GET_VERSION, "Code Ver:03.28.07", True, None),
    ],
)
def test_analyze_response(command, text, ok, dout1):
    result = analyze_response(SPECS[command], text)
    assert (result.ok, result.dout1) == (ok, dout1)


def test_codec12_simulator_helpers_roundtrip():
    frame = encode_codec12_command("setdigout 1")
    assert parse_codec12_command(frame) == "setdigout 1"
    response = decode_data_frame(build_codec12_response("DOUT1:1 Timeout:INFINITY"))
    assert response.text == "DOUT1:1 Timeout:INFINITY"
