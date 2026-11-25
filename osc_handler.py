import struct
import socket
import logging
from typing import Literal

OSC_HOST = "127.0.0.1"
OSC_PORT = 8001

logger = logging.getLogger(__name__)

def osc_string(value):
    encoded = value.encode("utf-8") + b"\0"
    return encoded + b"\0" * (-len(encoded) % 4)


def osc_float(address, value):
    return osc_string(address) + osc_string(",f") + struct.pack(">f", value)

class OscHandler:
    def __init__(self):
        self.osc_host = OSC_HOST
        self.osc_port = OSC_PORT
        self._levels: dict[str, dict[str, float]] = {}
        self._audio_gains: dict[str, float] = {}
        
        # Setup UDP socket to send OSC messages to openFrameworks application
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logger.info(f"OscHandler initialized: {OSC_HOST}:{OSC_PORT}")

    def set_level(
        self, address: str, source: Literal["audio", "midi"], value: float
    ) -> None:
        levels = self._levels.setdefault(address, {})
        old_value = levels.get(source, 0.0)
        levels[source] = max(0.0, min(1.0, value))
        
        self._send_level(address)

    def set_audio_gain(self, address: str, value: float) -> None:
        self._audio_gains[address] = max(0.0, min(1.0, value))
        if address in self._levels:
            self._send_level(address)

    def _send_level(self, address: str) -> None:
        levels = self._levels[address]
        audio = levels.get("audio", 0.0) * self._audio_gains.get(address, 1.0)
        combined = min(1.0, levels.get("midi", 0.0) + audio)

        try:
            self.udp_socket.sendto(
                osc_float(address, combined), (self.osc_host, self.osc_port)
            )
        except Exception as e:
            logger.error(f"Failed to send OSC message to {self.osc_host}:{self.osc_port}: {e}")
