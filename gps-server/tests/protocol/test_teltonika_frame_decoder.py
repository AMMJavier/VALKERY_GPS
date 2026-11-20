"""Reconstrucción de tramas desde el flujo TCP.

Referencia Traccar: TeltonikaFrameDecoderTest.java
"""

import pytest

from valkery_gps.protocol.base import DataFrame, FrameTooLargeError, ImeiFrame, PingFrame, ProtocolError
from valkery_gps.protocol.teltonika.avl_builder import build_imei_frame
from valkery_gps.protocol.teltonika.frame_decoder import TeltonikaFrameDecoder

from ..conftest import TEST_IMEI

IMEI_FRAME = bytes.fromhex("000f333536333037303432343431303133")  # ejemplo pág. 23 del PDF


def test_imei_from_pdf():
    frames = TeltonikaFrameDecoder().feed(IMEI_FRAME)
    assert frames == [ImeiFrame(imei=TEST_IMEI)]


def test_imei_byte_by_byte():
    decoder = TeltonikaFrameDecoder()
    frames = []
    for b in IMEI_FRAME:
        frames += decoder.feed(bytes([b]))
    assert frames == [ImeiFrame(imei=TEST_IMEI)]


def test_data_fragmented_byte_by_byte(pdf_example):
    decoder = TeltonikaFrameDecoder()
    frames = []
    for i, b in enumerate(pdf_example):
        out = decoder.feed(bytes([b]))
        if i < len(pdf_example) - 1:
            assert out == []
        frames += out
    assert frames == [DataFrame(raw=pdf_example)]
    assert decoder.pending_bytes == 0


def test_concatenated_imei_data_ping_and_partial(pdf_example):
    decoder = TeltonikaFrameDecoder()
    stream = IMEI_FRAME + pdf_example + b"\xff" + pdf_example
    frames = decoder.feed(stream[:-10])
    assert frames == [ImeiFrame(TEST_IMEI), DataFrame(pdf_example), PingFrame()]
    assert decoder.feed(stream[-10:]) == [DataFrame(pdf_example)]


def test_frame_too_large():
    decoder = TeltonikaFrameDecoder(max_frame_bytes=100)
    with pytest.raises(FrameTooLargeError):
        decoder.feed(bytes.fromhex("00000000" "00001000"))


def test_zero_length_rejected():
    with pytest.raises(FrameTooLargeError):
        TeltonikaFrameDecoder().feed(bytes(8))


def test_bad_preamble():
    with pytest.raises(ProtocolError):
        # 2 bytes en cero (no es IMEI) pero preámbulo de datos incompleto
        TeltonikaFrameDecoder().feed(bytes.fromhex("0000ffff00000010"))


def test_imei_too_long():
    with pytest.raises(ProtocolError):
        TeltonikaFrameDecoder().feed(b"\x00\x40" + b"1" * 64)


def test_imei_non_digit():
    with pytest.raises(ProtocolError):
        TeltonikaFrameDecoder().feed(build_imei_frame("35630704244101A"))
