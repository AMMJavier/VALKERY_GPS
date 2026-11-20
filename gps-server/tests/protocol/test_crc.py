from valkery_gps.protocol.teltonika.crc import crc16_ibm

from ..conftest import PDF_EXAMPLE_HEX


def test_standard_check_value():
    # Valor de verificación estándar de CRC-16/ARC (IBM) para "123456789".
    assert crc16_ibm(b"123456789") == 0xBB3D


def test_pdf_example_crc():
    raw = bytes.fromhex(PDF_EXAMPLE_HEX)
    length = int.from_bytes(raw[4:8], "big")
    assert crc16_ibm(raw[8 : 8 + length]) == 0x3FCA


def test_empty():
    assert crc16_ibm(b"") == 0
