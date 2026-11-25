from dataclasses import asdict, dataclass
from enum import Enum

from PyQt6.QtWidgets import QLabel


KEY_PRESS_TO_FB_MAP = {
    1: 0, # If key 1 is pressed, load to framebuffer 0
    2: 1, # If key 2 is pressed, load to framebuffer 1
    3: 2  # If key 3 is pressed, load to framebuffer 2
}

FRAME_BUFFER_STATE = {
    0: "<empty>",
    1: "<empty>",
    2: "<empty>",
}

class FrameBufferHandler:
    def __init__(self):
        self.framebuffer_status = FRAME_BUFFER_STATE.copy()


    def load_to_fb(self, fb: int, name: str | None) -> str|None:
        # Implement the logic to load to the specified framebuffer
        for fb_name, current_name in self.framebuffer_status.items():
            if current_name == name:
                name = None
            self.framebuffer_status[fb_name] = name
        if name is None:
            return "<empty>"
        return name

