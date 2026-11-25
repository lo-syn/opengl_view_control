from .osc import OSC_HOST, OSC_PORT, osc_string, OscHandler

class ShaderHandler:
    """Route captured PCM to one explicitly selected output device."""

    def __init__(self, osc_handler: OscHandler):
        self.osc_handler = osc_handler

    def send_shader(self, name, reset: bool = False):
            if reset:
                packet = osc_string("/shader") + osc_string(",s") + osc_string("reset")
                self.osc_handler.udp_socket.sendto(packet, (OSC_HOST, OSC_PORT))
                return
            else:
                packet = osc_string("/shader") + osc_string(",s") + osc_string(name)
                self.osc_handler.udp_socket.sendto(packet, (OSC_HOST, OSC_PORT))
                return