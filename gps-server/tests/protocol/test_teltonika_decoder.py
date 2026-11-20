"""Decodificación de Codec 8, 8 Extended y respuestas Codec 12.

Referencia Traccar: TeltonikaProtocolDecoderTest.java
"""

from datetime import UTC, datetime

import pytest

from valkery_gps.protocol.base import (
    AvlPacket,
    AvlRecord,
    CommandResponse,
    CrcError,
    ProtocolError,
    UnsupportedCodecError,
)
from valkery_gps.protocol.teltonika.avl_builder import build_avl_frame
from valkery_gps.protocol.teltonika.crc import crc16_ibm
from valkery_gps.protocol.teltonika.decoder import CODEC_8, CODEC_8_EXT, decode_data_frame
from valkery_gps.protocol.teltonika.io_elements import interpret

from ..conftest import load_traccar_vectors


def _reframe(body: bytes) -> bytes:
    """Arma una trama válida (cabecera + CRC) alrededor de un cuerpo."""
    return b"\x00" * 4 + len(body).to_bytes(4, "big") + body + crc16_ibm(body).to_bytes(4, "big")


# --------------------------------------------------------------------- PDF


def test_pdf_example(pdf_example):
    packet = decode_data_frame(pdf_example)
    assert isinstance(packet, AvlPacket)
    assert packet.codec == CODEC_8
    assert len(packet.records) == 1

    r = packet.records[0]
    assert r.timestamp == datetime(2013, 7, 17, 6, 34, 9, 140000, tzinfo=UTC)
    assert r.priority == 0
    # El PDF rotula N/E al revés: el primer campo es longitud.
    assert r.longitude == pytest.approx(25.2618832)
    assert r.latitude == pytest.approx(54.6990336)
    assert r.altitude == 148
    assert r.angle == 0  # el PDF dice 214º, pero el campo es 0x0000
    assert r.satellites == 18  # 0x12; el PDF dice "12"
    assert r.speed == 0
    assert r.event_io_id == 0
    assert len(r.io) == 30
    assert r.io[240] == 0  # movement
    assert r.io[21] == 4  # gsm signal
    assert r.io[66] == 0x2E9F  # external voltage 11935 mV
    assert r.io[241] == 0x601A  # operador


def test_pdf_example_interpreted(pdf_example):
    attrs = interpret(decode_data_frame(pdf_example).records[0].io)
    assert attrs["external_voltage"] == 11935
    assert attrs["gnss_pdop"] == pytest.approx(1.1)
    assert attrs["gnss_hdop"] == pytest.approx(0.7)
    assert attrs["io_22"] == 1  # desconocido: se conserva


# --------------------------------------------------------------------- Traccar


VECTORS = load_traccar_vectors()


@pytest.mark.parametrize("vector", VECTORS, ids=[f"{v['codec']}-{i}" for i, v in enumerate(VECTORS)])
def test_traccar_vectors(vector):
    message = decode_data_frame(bytes.fromhex(vector["hex"]))
    if vector["kind"] == "avl":
        assert isinstance(message, AvlPacket)
        assert len(message.records) == vector["records"]
        for r in message.records:
            assert -180 <= r.longitude <= 180
            assert -90 <= r.latitude <= 90
    else:
        assert isinstance(message, CommandResponse)
        assert message.text.startswith(vector["text_prefix"].strip())


def test_traccar_vectors_cover_all_codecs():
    codecs = {v["codec"] for v in VECTORS}
    assert {"08", "8e", "0c"} <= codecs


def test_codec12_response_traccar():
    hexa = next(v["hex"] for v in VECTORS if v["codec"] == "0c" and "FM2" in v["text_prefix"])
    response = decode_data_frame(bytes.fromhex(hexa))
    assert response.text.startswith("#FM2=")


# --------------------------------------------------------------------- ida y vuelta


def _record(**overrides) -> AvlRecord:
    base = dict(
        timestamp=datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC),
        priority=1,
        longitude=-78.4678123,
        latitude=-0.1807456,
        altitude=-12,
        angle=275,
        satellites=9,
        speed=43,
        event_io_id=239,
        io={239: 1, 240: 1, 179: 0, 66: 12850, 16: 123456, 11: 2**63 + 5},
    )
    base.update(overrides)
    return AvlRecord(**base)


@pytest.mark.parametrize("codec", [CODEC_8, CODEC_8_EXT])
def test_roundtrip_negative_coordinates_multiple_records(codec):
    records = [_record(), _record(speed=0, satellites=0, angle=0)]
    packet = decode_data_frame(build_avl_frame(records, codec))
    assert packet.codec == codec
    assert packet.records == records


def test_codec8e_variable_length_and_two_byte_ids():
    rec = _record(event_io_id=385, io={385: b"\x01\x02\x03", 1000: 7, 239: 0})
    packet = decode_data_frame(build_avl_frame([rec], CODEC_8_EXT))
    assert packet.records[0].io == {385: b"\x01\x02\x03", 1000: 7, 239: 0}
    assert packet.records[0].event_io_id == 385


# --------------------------------------------------------------------- errores


def test_crc_mismatch(pdf_example):
    corrupted = bytearray(pdf_example)
    corrupted[30] ^= 0xFF
    with pytest.raises(CrcError):
        decode_data_frame(bytes(corrupted))


def test_length_mismatch(pdf_example):
    with pytest.raises(ProtocolError):
        decode_data_frame(pdf_example + b"\x00")


def test_record_count_mismatch(pdf_example):
    body = bytearray(pdf_example[8:-4])
    body[-1] = 2  # número de datos 2 != 1
    with pytest.raises(ProtocolError, match="inconsistente"):
        decode_data_frame(_reframe(bytes(body)))


def test_truncated_record():
    with pytest.raises(ProtocolError, match="truncada"):
        decode_data_frame(_reframe(bytes([CODEC_8, 1]) + b"\x00" * 10 + b"\x01"))


def test_trailing_bytes(pdf_example):
    body = pdf_example[8:-5] + b"\x00\x01"  # byte extra antes del número de datos
    with pytest.raises(ProtocolError):
        decode_data_frame(_reframe(body))


def test_unsupported_codec():
    with pytest.raises(UnsupportedCodecError):
        decode_data_frame(_reframe(bytes([0x10, 0, 0])))


def test_codec12_command_type_not_accepted_from_device():
    body = bytes([0x0C, 1, 0x05]) + (4).to_bytes(4, "big") + b"test" + b"\x01"
    with pytest.raises(UnsupportedCodecError):
        decode_data_frame(_reframe(body))


def test_codec12_response():
    text = b"DOUT1:1 Timeout:INFINITY"
    body = bytes([0x0C, 1, 0x06]) + len(text).to_bytes(4, "big") + text + b"\x01"
    response = decode_data_frame(_reframe(body))
    assert isinstance(response, CommandResponse)
    assert response.text == "DOUT1:1 Timeout:INFINITY"
