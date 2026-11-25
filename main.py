import sys
import json
import logging
from pathlib import Path

from handlers.browser import BrowserHandler
from handlers.midi import MidiHandler
from handlers.osc import OscHandler, OSC_HOST, OSC_PORT, osc_string
from handlers.audio import (
    AudioHandler,
    AudioOutputRouter,
    BLUETOOTH_CAPTURE_SINK,
)
from schema import DefaultMenuItem, ShaderItem, SettingsMenuItem, ShaderPackItem

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
)

logger = logging.getLogger(__name__)


class DefaultListWidget(QListWidget):
    # Create navigateable list widget
    activateCurrentItem = pyqtSignal(QListWidgetItem)
    navigateRight = pyqtSignal()
    navigateLeft = pyqtSignal()
    closeRequested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
         # Handle key events for activating items and navigating
        if event.key() == Qt.Key.Key_Escape:
            self.closeRequested.emit()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.currentItem()
            if item is not None:
                self.activateCurrentItem.emit(item)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Right:
            self.navigateRight.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Left:
            self.navigateLeft.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class DefaultMenu(QWidget):
    def __init__(self):
        super().__init__()

        settings_path = Path(__file__).resolve().parent / "configs" / "settings.json"
        with settings_path.open("r", encoding="utf-8") as settings_file:
            self.app_settings = json.load(settings_file)

        default_shader_dir = Path(self.app_settings["shaders"]["directory_path"])

        self.settings = {
            "enable_midi": SettingsMenuItem(
                on_state_msg="enabled",
                off_state_msg="disabled",
                linked_function=self.set_midi_enabled,
            ),
            "enable_audio_input": SettingsMenuItem(
                status_labels=["disabled", "audio_file"],
                linked_function=self.set_audio_input_enabled,
            ),
            "enable_audio_output": SettingsMenuItem(
                on_state_msg="enabled",
                off_state_msg="disabled",
                linked_function=self.set_audio_output_enabled,
            ),
        }

        # Add handlers
        self.osc_handler = OscHandler()
        self.audio_handler = None
        self.active_shader = None
        self.active_shader_owner = None

        # Audio mode state: 0=disabled, 1=audio_file
        self.audio_mode = 0
        self.file_audio_handler = None
        self.output_router = AudioOutputRouter(self._audio_output_failed)
        self.output_device_index = -1
        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self._audio_outputs_changed)

        self.setWindowTitle("Default menu")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        # Change window size to match desired dimensions (e.g. 680x420)
        self.setFixedSize(680, 420)
        self.setStyleSheet(
            "QWidget { background-color: #000; color: #fff; }"
            "QListWidget { border: 0; }"
            "QListWidget::item { padding: 0 6px; }"
            "QListWidget::item:selected { background-color: #555; color: #fff; }"
            "QListWidget QWidget { background-color: transparent; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Setup label for the title of the current menu
        self.title = QLabel()
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("color: #fff; font-size: 9pt;")
        layout.addWidget(self.title)

        self.status_bar = QLabel()
        self.status_bar.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.status_bar.setMinimumHeight(28)
        self.status_bar.setStyleSheet(
            "QLabel { background-color: #222; color: #fff; padding: 4px 6px; }"
        )
        layout.addWidget(self.status_bar)
        self.update_active_shader_status()

        self.list_widget = DefaultListWidget()
        self.list_widget.setSpacing(3)

        # Connect actions to functions
        self.status_labels: dict[str, QLabel] = {}
        self.shader_status_labels: dict[tuple[str, str], QLabel] = {}
        self.list_widget.activateCurrentItem.connect(self.activate_item)
        self.list_widget.currentRowChanged.connect(self.update_selected_row)

        self.list_widget.navigateRight.connect(self.navigate_right)
        self.list_widget.navigateLeft.connect(self.navigate_left)
        self.list_widget.closeRequested.connect(self.close)

        layout.addWidget(self.list_widget)

        # Create message bar
        self.message_bar = QLabel()
        self.message_bar.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.message_bar.setWordWrap(True)
        self.message_bar.setMinimumHeight(28)
        self.message_bar.setStyleSheet(
            "QLabel { background-color: #222; color: #fff; padding: 4px 6px; }"
        )
        layout.addWidget(self.message_bar)

        self.current_page = "shaders"
        self.midi_handler = None
        self.midi_timer = None

        # Show shader menu by default
        
        self.browser_handler = BrowserHandler(default_shader_dir)
        self.current_browser_filter = self.app_settings["shaders"]["file_extensions"]
        self.show_shaders(self.browser_handler)

    def update_selected_row(self, selected_row: int):
        self.clear_message()
        for row_index in range(self.list_widget.count()):
            row = self.list_widget.itemWidget(self.list_widget.item(row_index))
            if row is not None:
                background = "#555" if row_index == selected_row else "transparent"
                row.setStyleSheet(f"background-color: {background};")

    def _populate_menu(
        self,
        menu_items: dict[str, DefaultMenuItem],
        offset: bool = False,
        after_item: QListWidgetItem | None = None,
        pack_name: str | None = None,
    ):
        insertion_row = self.list_widget.count()
        if after_item is not None:
            insertion_row = self.list_widget.row(after_item)
            if insertion_row < 0:
                raise ValueError("Menu item does not belong to this list")
            insertion_row += 1

        for name, menu_item in menu_items.items():
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setData(Qt.ItemDataRole.UserRole + 1, offset)
            item.setData(Qt.ItemDataRole.UserRole + 2, pack_name)
            row = self._create_row(name, menu_item, offset, pack_name)
            self.list_widget.insertItem(insertion_row, item)
            insertion_row += 1
            item.setSizeHint(row.sizeHint())
            self.list_widget.setItemWidget(item, row)

    def _collapse_menu(self, pack_name: str):
        for row_index in reversed(range(self.list_widget.count())):
            item = self.list_widget.item(row_index)
            if item.data(Qt.ItemDataRole.UserRole + 2) != pack_name:
                continue

            name = item.data(Qt.ItemDataRole.UserRole)
            self.shader_status_labels.pop((pack_name, name), None)
            row = self.list_widget.itemWidget(item)
            self.list_widget.removeItemWidget(item)
            self.list_widget.takeItem(row_index)
            if row is not None:
                row.deleteLater()

    def show_shaders(self, browser_handler: BrowserHandler):
        self.clear_message()
        # Show shader menu
        self.current_page = "shaders"
        self.title.setText("SHADER")
        self.list_widget.clear()
        self.shader_status_labels.clear()
        self.current_browser_filter = [".frag", ".fs"]
        browser_handler.populate(self.list_widget, browser_filter=self.current_browser_filter)

        self.active_shader_pack = None
        self.list_widget.setCurrentRow(0)

    def show_settings(self):
        self.clear_message()
        # Show settings menu
        self.current_page = "settings"
        self.title.setText("SETTINGS")
        self.list_widget.clear()
        self._populate_menu(self.settings)
        self.list_widget.setCurrentRow(0)

    def show_browser(self):
        self.clear_message()
        # Show browser menu
        self.current_page = "browser"
        self.title.setText("BROWSER")
        try:
            self.browser_handler.populate(self.list_widget)
        except OSError as error:
            self._update_message(f"Could not read browser directory: {error}")
            return
        self.list_widget.setCurrentRow(0)

    def navigate_right(self):
        if self.current_page == "shaders":
            self.show_settings()
        elif self.current_page == "settings":
            self.show_browser()

    def navigate_left(self):
        if self.current_page == "browser":
            self.show_settings()
        elif self.current_page == "settings":
            self.show_shaders()

    def clear_message(self):
        self.message_bar.clear()

    def update_active_shader_status(self):
        # Add active shader to status bar
        shader_name = self.active_shader if self.active_shader is not None else ""
        self.status_bar.setText(f"Active Shader: {shader_name}")

    def set_midi_enabled(self, enabled: bool) -> bool:
        if enabled:
            if self.midi_handler is not None:
                self.status_labels["enable_midi"].setText("enabled")
            try:
                midi_handler = MidiHandler(self.osc_handler)
                midi_handler.open_midi_input()
            except Exception as error:
                self.status_labels["enable_midi"].setText("disabled")
                self._update_message(str(error))
                return False

            self.midi_handler = midi_handler
            self.midi_timer = QTimer(self)
            self.midi_timer.timeout.connect(self.midi_handler.read_midi)
            self.midi_timer.start(5)

            return True

        # Handles disabling QTimer
        if self.midi_timer is not None:
            self.midi_timer.stop()
            self.midi_timer = None
        # Handles disabling MIDI input
        if self.midi_handler is not None:
            self.midi_handler.close_midi_input()
            self.midi_handler = None
        return False

    def set_audio_input_enabled(self, enabled: bool) -> bool:
        """
        Cycle through audio modes:
        - Disabled (0) → Audio File (1) → Disabled (0)
        
        When enabled=True, advance to next mode.
        When enabled=False, go to disabled mode.
        """
        try:
            if not enabled:
                self._stop_all_audio()
                self.audio_mode = 0
                return False
            
            self.audio_mode = (self.audio_mode + 1) % 2
            if self.audio_mode == 1:
                self._stop_all_audio()
                if self.file_audio_handler is None:
                    self.file_audio_handler = AudioHandler(self.osc_handler)
                    self.file_audio_handler.set_output_router(self.output_router)
                self.file_audio_handler.play()
                self._update_message(f"Playing audio file: {self.file_audio_handler.active_audio_file}")
                return True
            
            # audio_mode == 0
            else:
                self._stop_all_audio()
                return False
        except (ImportError, FileNotFoundError) as error:
            # Only catch setup errors, not connection errors
            self._stop_all_audio()
            self.audio_mode = 0
            self._update_message(f"Could not enable audio: {error}")
            return False

    def _apply_audio_output(self) -> None:
        if self.file_audio_handler is not None:
            self.file_audio_handler.set_output_router(self.output_router)

    def _audio_output_failed(self, name: str) -> None:
        # Handles closing output router and logging failure
        self.output_router.disconnect()
        self._apply_audio_output()
        self.settings["enable_audio_output"].state = False
        if self.current_page == "settings" and "enable_audio_output" in self.status_labels:
            self.status_labels["enable_audio_output"].setText("disabled")
        self.message_bar.setText(f"Unable to connect to {name}")

    def _audio_outputs_changed(self) -> None:
        device = self.output_router.device
        if device is not None and not any(
            candidate.id() == device.id() for candidate in self._available_audio_outputs()
        ):
            self._audio_output_failed(device.description())

    @staticmethod
    def _available_audio_outputs():
        """Return a list of available audio output devices, excluding the Bluetooth capture sink."""
        return [
            device
            for device in QMediaDevices.audioOutputs()
            if device.description() != BLUETOOTH_CAPTURE_SINK
        ]

    def set_audio_output_enabled(self, enabled: bool) -> bool:
        if not enabled:
            self.output_router.disconnect()
            self._apply_audio_output()
            self.output_device_index = -1
            self.update_active_shader_status()
            return False

        devices = self._available_audio_outputs()
        if not devices:
            self._audio_output_failed("output device")
            self.output_device_index = -1
            return False
        self.output_device_index += 1
        if self.output_device_index >= len(devices):
            return self.set_audio_output_enabled(False)
        device = devices[self.output_device_index]
        try:
            connected = self.output_router.connect(device)
        except (OSError, RuntimeError):
            logger.exception("Could not open output device %s", device.description())
            connected = False
        if not connected:
            self._audio_output_failed(device.description())
            return False
        self._apply_audio_output()
        self.update_active_shader_status()
        return True
    
    def _stop_all_audio(self):
        """Stop all audio handlers."""
        if self.file_audio_handler is not None:
            try:
                self.file_audio_handler.stop()
            except Exception:
                pass

    def _update_message(self, text: str) -> None:
        """Update message bar text and immediately refresh the GUI """
        self.message_bar.setText(text)
        QApplication.processEvents()

    def _create_row(
        self, name: str, menu_item: DefaultMenuItem, offset: bool = False,
        pack_name: str | None = None,
    ):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(40 if offset else 0, 0, 0, 0)
        row_layout.addWidget(QLabel(name))
        row_layout.addStretch()

        
        # Special handling for audio mode display
        if pack_name is None and name == "enable_audio_input":
            status = QLabel(self.settings[name].status_labels[self.audio_mode])
        elif (
            pack_name is None
            and name == "enable_audio_output"
            and self.output_router.device is not None
        ):
            status = QLabel(self.output_router.device.description())
        elif pack_name is None and name in self.shader_packs:
            status = QLabel()

        elif menu_item.state:
            status = QLabel(menu_item.on_state_msg)
        else:
            status = QLabel(menu_item.off_state_msg)
        
        status.setObjectName("activeStatus")
        if pack_name is None:
            self.status_labels[name] = status
        else:
            self.shader_status_labels[(pack_name, name)] = status
        row_layout.addWidget(status)
        return row

    def _run_settings_option(self, name: str):
        if name not in self.settings.keys():
            self._update_message("Attempting to run missing setting")
            return
        current_setting: SettingsMenuItem = self.settings[name]
        current_state = current_setting.state
        
        # Special handling for audio mode cycling - always advance mode
        if name == "enable_audio_input":
            # For audio, we always pass True to cycle through modes
            # We never toggle off/on, we cycle between disabled and file audio
            state = current_setting.linked_function(True)
            
            # Always keep button state as True (we're in audio mode selection)
            # This ensures next press advances to next mode, not toggles back
            current_setting.state = True
            
            # Update label with current mode name
            mode_name = self.settings[name].status_labels[self.audio_mode]
            self.status_labels[name].setText(mode_name)
        elif name == "enable_audio_output":
            state = current_setting.linked_function(True)
            current_setting.state = state
            device = self.output_router.device
            self.status_labels[name].setText(
                device.description() if device is not None else current_setting.off_state_msg
            )
        else:
            # Normal toggle for other settings
            state = current_setting.linked_function(not current_state)
            current_setting.state = state
            
            if state:
                self.status_labels[name].setText(current_setting.on_state_msg)
            else:
                self.status_labels[name].setText(current_setting.off_state_msg)

    def _run_shader_option(self, name: str, pack_name: str):
        pack = self.shader_packs[pack_name]
        if name not in pack.shaders:
            self._update_message("Attempting to run missing shader")
            return
        if self.active_shader_pack is not pack:
            self.active_shader_pack = pack
            self.send_shader_pack(pack_name)
        current_shader: ShaderItem = pack.shaders[name]
        status = self.shader_status_labels[(pack_name, name)]
        # Reset if already active
        if self.active_shader == name and self.active_shader_owner == pack_name:
            current_shader.state = False
            status.setText(current_shader.off_state_msg)
            self.active_shader = None
            self.active_shader_owner = None
            self.update_active_shader_status()
            self.send_shader("reset")
            return
        # Set off message for previous shader
        if self.active_shader is not None:
            previous_shader = self.shader_packs[self.active_shader_owner].shaders[self.active_shader]
            previous_shader.state = False
            previous_status = self.shader_status_labels.get(
                (self.active_shader_owner, self.active_shader)
            )
            if previous_status is not None:
                previous_status.setText(previous_shader.off_state_msg)

        # Set active shader
        self.active_shader = name
        self.active_shader_owner = pack_name
        self.update_active_shader_status()
        current_shader.state = True
        status.setText(current_shader.on_state_msg)
        self.send_shader(name)

    def activate_item(self, item):
        self.clear_message()
        name = item.data(Qt.ItemDataRole.UserRole)
        if Path(name).is_dir():
            self.browser_handler.toggle_directory(self.list_widget, item, self.current_browser_filter)
            return

        if self.current_page == "settings":
            self._run_settings_option(name)
            return
        if self.current_page == "shaders":

            self.send_shader(name)
            return
        if self.current_page == "browser":
            try:
                self.browser_handler.toggle_directory(self.list_widget, item)
            except OSError as error:
                self._update_message(f"Could not read directory: {error}")
            return

    def send_shader(self, name):
        packet = osc_string("/shader") + osc_string(",s") + osc_string(name)
        self.osc_handler.udp_socket.sendto(packet, (OSC_HOST, OSC_PORT))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Clean up all resources on application exit.
        
        Stop audio before exiting.
        """
        logger.info("Application closing - cleaning up resources...")

        # Stop all audio playback
        self.set_midi_enabled(False)
        self._stop_all_audio()
        self.output_router.disconnect()
        
        # Close OSC socket
        self.osc_handler.udp_socket.close()
        
        super().closeEvent(event)


def main():
    # Configure logging to show all debug messages
    # Set level to INFO for production, DEBUG for troubleshooting
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    app = QApplication(sys.argv)
    menu = DefaultMenu()

    screen_geometry = app.primaryScreen().availableGeometry()
    x_position = (screen_geometry.width() - menu.width()) // 2
    y_position = screen_geometry.height() - menu.height() - 18
    menu.move(screen_geometry.x() + x_position, screen_geometry.y() + y_position)
    menu.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
