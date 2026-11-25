import mido
import json
from pathlib import Path

from .osc import OscHandler



# Import MIDI related settings from JSON file
with open(Path(__file__).resolve().parent.parent / "configs" / "settings.json", "r") as f:
    settings = json.load(f)

MIDI_INPUT_NAME: str = settings["midi"].get("midi_input_name")  # Default MIDI input name
MIDI_CC_TO_OSC: dict[int, str] = {int(k): v for k, v in settings["midi"]["midi_cc_to_osc"].items()}
MIDI_AUDIO_GAIN_CC_TO_OSC: dict[int, str] = {int(k): v for k, v in settings["midi"]["midi_audio_gain_cc_to_osc"].items()}

class MidiHandler:
    def __init__(self, osc_handler: OscHandler):
        self.midi_input_name = MIDI_INPUT_NAME
        self.midi_input = None
        self.osc_handler = osc_handler

    def open_midi_input(self):
        if self.midi_input is not None:
            self.midi_input.close()
        midi_ports = mido.get_input_names()
        if self.midi_input_name in midi_ports:
            self.midi_input = mido.open_input(self.midi_input_name)
        else:
            raise ValueError(f"Invalid MIDI input name: '{self.midi_input_name}', Available device names are found below: {midi_ports}")

    def close_midi_input(self):
        if self.midi_input is not None:
            self.midi_input.close()
            self.midi_input = None

    def read_midi(self):
        for message in self.midi_input.iter_pending():
            if message.type != "control_change":
                continue
            value = message.value / 127.0
            address = MIDI_CC_TO_OSC.get(message.control)
            if address is not None:
                self.osc_handler.set_level(address, "midi", value)
                continue
            address = MIDI_AUDIO_GAIN_CC_TO_OSC.get(message.control)
            if address is not None:
                self.osc_handler.set_audio_gain(address, value)

    def read_midi_messages(self):
        if self.midi_input is not None:
            return list(self.midi_input.iter_pending())
        return []