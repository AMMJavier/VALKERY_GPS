from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "teltonika"

# Ejemplo de la pág. 20 del PDF «FMB1YX Protocols V0.15» (152 bytes, 1 registro).
PDF_EXAMPLE_HEX = (
    "000000000000008c08010000013feb55ff74000f0ea850209a690000940000120000001e"
    "09010002000300040016014703f0001504c8000c0900730a00460b00501300464306d744"
    "0000b5000bb60007422e9f180000cd0386ce000107c700000000f10000601a4600000134"
    "4800000bb84900000bb84a00000bb84c00000000024e0000000000000000cf0000000000"
    "0000000100003fca"
)

# IMEI de ejemplo del PDF (pág. 23). Nunca usar IMEIs reales en pruebas.
TEST_IMEI = "356307042441013"


@pytest.fixture
def pdf_example() -> bytes:
    return bytes.fromhex(PDF_EXAMPLE_HEX)


def load_traccar_vectors() -> list[dict]:
    return json.loads((FIXTURES / "traccar_vectors.json").read_text(encoding="utf-8"))["vectors"]
