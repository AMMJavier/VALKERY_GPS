"""Protocolo Teltonika (FMC920).

Referencia Traccar: protocol/TeltonikaProtocol.java
"""

from .decoder import CODEC_8, CODEC_8_EXT, CODEC_12, decode_data_frame
from .encoder import encode_codec12_command, encode_imei_response, encode_records_ack
from .frame_decoder import TeltonikaFrameDecoder

__all__ = [
    "CODEC_8",
    "CODEC_8_EXT",
    "CODEC_12",
    "TeltonikaFrameDecoder",
    "decode_data_frame",
    "encode_codec12_command",
    "encode_imei_response",
    "encode_records_ack",
]
