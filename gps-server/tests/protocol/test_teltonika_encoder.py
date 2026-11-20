"""Codificación de respuestas y comandos Codec 12.

Referencia Traccar: TeltonikaProtocolEncoderTest.java
"""

import pytest

from valkery_gps.protocol.teltonika.encoder import (
    encode_codec12_command,
    encode_imei_response,
    encode_records_ack,
)


def test_imei_response():
    assert encode_imei_response(True) == b"\x01"
    assert encode_imei_response(False) == b"\x00"


def test_records_ack():
    # PDF pág. 23: ACK de 2 registros = 00000002
    assert encode_records_ack(2) == bytes.fromhex("00000002")
    with pytest.raises(ValueError):
        encode_records_ack(256)


def test_codec12_matches_traccar_vector():
    expected = bytes.fromhex("00000000000000140c01050000000c7365746469676f7574203131010000bed5")
    assert encode_codec12_command("setdigout 11") == expected


def test_codec12_binary_matches_traccar_vector():
    expected = bytes.fromhex("00000000000000100c01050000000803030000000185e8010000da8b")
    assert encode_codec12_command(bytes.fromhex("03030000000185E8")) == expected


def test_codec12_getinfo_teltonika_wiki_example():
    expected = bytes.fromhex("000000000000000f0c010500000007676574696e666f0100004312")
    assert encode_codec12_command("getinfo") == expected


def test_codec12_rejects_empty():
    with pytest.raises(ValueError):
        encode_codec12_command("")
