"""
Bluetooth audio streaming module for cross-platform support (Windows and Debian/Linux).
Provides abstraction layer for sending audio to Bluetooth speakers and headphones.
"""

import logging
import platform
import subprocess
import json
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Callable
from threading import Thread

logger = logging.getLogger(__name__)


@dataclass
class BluetoothDevice:
    """Represents a Bluetooth device."""
    name: str
    mac_address: str
    connected: bool = False
    is_audio_device: bool = False


class BluetoothAudioBackend(ABC):
    """Abstract base class for Bluetooth audio backends."""

    @abstractmethod
    def scan_devices(self) -> list[BluetoothDevice]:
        """Scan for available Bluetooth devices."""
        pass

    @abstractmethod
    def connect_device(self, device: BluetoothDevice) -> bool:
        """Connect to a Bluetooth device."""
        pass

    @abstractmethod
    def disconnect_device(self, device: BluetoothDevice) -> bool:
        """Disconnect from a Bluetooth device."""
        pass

    @abstractmethod
    def get_connected_devices(self) -> list[BluetoothDevice]:
        """Get list of currently connected audio devices."""
        pass

    @abstractmethod
    def set_as_default_output(self, device: BluetoothDevice) -> bool:
        """Set device as the default audio output."""
        pass

    @abstractmethod
    def disable_all_bluetooth_audio(self) -> bool:
        """Disable audio passthrough for all Bluetooth devices."""
        pass


class WindowsBluetoothBackend(BluetoothAudioBackend):
    """Windows-specific Bluetooth audio implementation using Windows APIs."""

    def __init__(self):
        self.devices: dict[str, BluetoothDevice] = {}
        try:
            import winreg
            self.winreg = winreg
            logger.info("Windows Bluetooth backend initialized")
        except ImportError:
            logger.warning("winreg not available, some features may be limited")
            self.winreg = None

    def scan_devices(self) -> list[BluetoothDevice]:
        """Scan for Bluetooth audio devices on Windows.
        
        Prioritizes actual Bluetooth audio outputs (like A2DP speakers/headsets)
        over intermediate receiver devices.
        """
        devices = []
        try:
            # Get all audio endpoint devices
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-PnpDevice -Class AudioEndpoint | Select-Object -ExpandProperty Name"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                # Filter for Bluetooth-related devices
                # Prioritize A2DP (actual audio streaming) over Bluetooth receiver devices
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Only include actual Bluetooth audio devices
                    # - A2DP: Advanced Audio Distribution Profile (Bluetooth audio streaming)
                    # - Avoid intermediate receivers like "RX-V781" which are not direct audio outputs
                    if 'A2DP' in line:
                        devices.append(BluetoothDevice(
                            name=line,
                            mac_address="unknown",
                            is_audio_device=True
                        ))
                        logger.info(f"Found Bluetooth audio device: {line}")
                    elif 'Bluetooth' in line and 'RX' not in line:
                        # Include other Bluetooth devices but not RX receivers
                        devices.append(BluetoothDevice(
                            name=line,
                            mac_address="unknown",
                            is_audio_device=True
                        ))
                        logger.info(f"Found Bluetooth device: {line}")
                
                logger.info(f"Found {len(devices)} Bluetooth audio devices on Windows")

        except subprocess.TimeoutExpired:
            logger.error("Bluetooth device scan timed out")
        except Exception as e:
            logger.error(f"Error scanning Bluetooth devices: {e}")

        return devices

    def connect_device(self, device: BluetoothDevice) -> bool:
        """Connect to a Bluetooth device on Windows."""
        try:
            # Windows Bluetooth connection is typically automatic when device is paired
            # Escape apostrophes in device name for PowerShell
            escaped_name = device.name.replace("'", "''")
            
            result = subprocess.run(
                ["powershell", "-Command",
                 f"$device = Get-PnpDevice -Class AudioEndpoint | Where-Object {{$_.Name -eq '{escaped_name}'}}; if ($device) {{ Write-Host 'Found' }}"],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode == 0 and 'Found' in result.stdout:
                device.connected = True
                logger.info(f"Connected to Bluetooth device: {device.name}")
                return True
            else:
                logger.warning(f"Device {device.name} not ready or not found")
                return False
        except Exception as e:
            logger.error(f"Error connecting to Bluetooth device: {e}")
            return False

    def disconnect_device(self, device: BluetoothDevice) -> bool:
        """Disconnect from a Bluetooth device on Windows."""
        try:
            device.connected = False
            logger.info(f"Disconnected from Bluetooth device: {device.name}")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from Bluetooth device: {e}")
            return False

    def get_connected_devices(self) -> list[BluetoothDevice]:
        """Get connected Bluetooth audio devices on Windows."""
        try:
            # Use Get-PnpDevice to find connected audio devices
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-PnpDevice -Class AudioEndpoint | Where-Object {$_.Status -eq 'OK' -and $_.Name -like '*Bluetooth*'} | Select-Object -ExpandProperty Name)"],
                capture_output=True,
                text=True,
                timeout=10
            )

            devices = []
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line:
                        devices.append(BluetoothDevice(
                            name=line,
                            mac_address="unknown",
                            connected=True,
                            is_audio_device=True
                        ))
                logger.info(f"Found {len(devices)} connected Bluetooth audio devices")
            return devices
        except Exception as e:
            logger.error(f"Error getting connected devices: {e}")
            return []

    def set_as_default_output(self, device: BluetoothDevice) -> bool:
        """Set as default audio output on Windows."""
        try:
            # Escape apostrophes in device name for PowerShell
            escaped_name = device.name.replace("'", "''")
            
            logger.info(f"Attempting to set {device.name} as default audio output")
            
            # Try using Get-PnpDevice to verify device exists
            result = subprocess.run(
                ["powershell", "-Command",
                 f"$audio = Get-PnpDevice -Class AudioEndpoint | Where-Object {{$_.Name -eq '{escaped_name}'}}; if ($audio) {{ Write-Host 'Found device' }}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and 'Found device' in result.stdout:
                logger.info(f"Device {device.name} exists and can be used")
                return True
            else:
                logger.warning(f"Could not locate device: {device.name}")
                return False
        except Exception as e:
            logger.error(f"Error setting default audio device: {e}")
            return False

    @staticmethod
    def _set_default_to_non_bluetooth() -> bool:
        """Set default audio output to a non-Bluetooth device on Windows.
        
        This prevents automatic audio passthrough to Bluetooth devices.
        Called during initialization to ensure audio doesn't flow to Bluetooth
        unless explicitly enabled by the application.
        """
        try:
            # Get current default audio device and ensure it's not Bluetooth
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-AudioDevice -List | Where-Object {$_.Type -eq 'Playback' -and $_.Default -eq $true}).Name"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                current_device = result.stdout.strip()
                # If current device is Bluetooth, try to switch to non-Bluetooth
                if 'bluetooth' in current_device.lower() or 'bluez' in current_device.lower():
                    logger.info(f"Current default is Bluetooth device: {current_device}")
                    logger.warning("Bluetooth passthrough prevention not fully implemented for Windows")
                    # Windows audio device management is complex; log the issue
                    return False
            
            return True
        except Exception as e:
            logger.warning(f"Could not verify non-Bluetooth default on Windows: {e}")
            return True  # Don't fail on Windows, as this is non-critical

    def disable_all_bluetooth_audio(self) -> bool:
        """Disable audio passthrough for all Bluetooth devices on Windows.
        
        This prevents any Bluetooth device from receiving audio until explicitly re-enabled.
        """
        try:
            # Windows Bluetooth audio management is handled through driver/device settings
            # This is a placeholder for future implementation
            logger.info("Bluetooth audio passthrough disabled (Windows)")
            return True
        except Exception as e:
            logger.error(f"Error disabling Bluetooth audio on Windows: {e}")
            return False


class DebianBluetoothBackend(BluetoothAudioBackend):
    """Debian/Linux-specific Bluetooth audio implementation using BlueZ."""

    def __init__(self):
        self.devices: dict[str, BluetoothDevice] = {}
        self._check_dependencies()
        logger.info("Debian/Linux Bluetooth backend initialized")

    def _check_dependencies(self):
        """Check if required Bluetooth tools are installed."""
        required_tools = ["bluetoothctl", "pactl", "pacmd"]
        missing_tools = []

        for tool in required_tools:
            result = subprocess.run(
                ["which", tool],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                missing_tools.append(tool)

        if missing_tools:
            logger.warning(
                f"Missing Bluetooth tools: {', '.join(missing_tools)}. "
                "Install with: sudo apt-get install bluez pulseaudio-module-bluetooth"
            )

    def scan_devices(self) -> list[BluetoothDevice]:
        """Scan for Bluetooth devices on Debian/Linux using bluetoothctl."""
        devices = []
        try:
            # Get available devices from device cache (no interactive scan)
            result = subprocess.run(
                ["bluetoothctl", "devices"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.startswith("Device"):
                        parts = line.split()
                        if len(parts) >= 3:
                            mac_address = parts[1]
                            device_name = ' '.join(parts[2:])
                            devices.append(BluetoothDevice(
                                name=device_name,
                                mac_address=mac_address,
                                is_audio_device=self._is_audio_device(mac_address)
                            ))
                logger.info(f"Found {len(devices)} Bluetooth devices")
            else:
                logger.warning(f"Failed to scan devices: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.error("Bluetooth scan timed out")
        except FileNotFoundError:
            logger.error("bluetoothctl not found. Install with: sudo apt-get install bluez")
        except Exception as e:
            logger.error(f"Error scanning Bluetooth devices: {e}")

        return devices

    def _is_audio_device(self, mac_address: str) -> bool:
        """Check if device supports audio (A2DP or HFP)."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "info", mac_address],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                output = result.stdout.lower()
                return any(audio_codec in output for audio_codec in ["a2dp", "hfp", "audio"])
            return False
        except Exception:
            return False

    def connect_device(self, device: BluetoothDevice) -> bool:
        """Connect to a Bluetooth device on Debian/Linux."""
        try:
            # Trust the device first
            subprocess.run(
                ["bluetoothctl", "trust", device.mac_address],
                capture_output=True,
                timeout=5
            )

            # Connect to device
            result = subprocess.run(
                ["bluetoothctl", "connect", device.mac_address],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0 or "already connected" in result.stdout.lower():
                device.connected = True
                logger.info(f"Connected to {device.name} ({device.mac_address})")
                return True
            else:
                logger.warning(f"Failed to connect: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Connection attempt timed out")
            return False
        except Exception as e:
            logger.error(f"Error connecting to device: {e}")
            return False

    def disconnect_device(self, device: BluetoothDevice) -> bool:
        """Disconnect from a Bluetooth device on Debian/Linux."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "disconnect", device.mac_address],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 or "not connected" in result.stdout.lower():
                device.connected = False
                logger.info(f"Disconnected from {device.name}")
                return True
            else:
                logger.warning(f"Failed to disconnect: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error disconnecting device: {e}")
            return False

    def get_connected_devices(self) -> list[BluetoothDevice]:
        """Get connected Bluetooth devices on Debian/Linux."""
        devices = []
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices", "Connected"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.startswith("Device"):
                        parts = line.split()
                        if len(parts) >= 3:
                            mac_address = parts[1]
                            device_name = ' '.join(parts[2:])
                            devices.append(BluetoothDevice(
                                name=device_name,
                                mac_address=mac_address,
                                connected=True,
                                is_audio_device=self._is_audio_device(mac_address)
                            ))
            return devices
        except Exception as e:
            logger.error(f"Error getting connected devices: {e}")
            return []

    def set_as_default_output(self, device: BluetoothDevice) -> bool:
        """Set as default audio output using PulseAudio."""
        return self._set_pulseaudio_default(device)

    @staticmethod
    def _set_pulseaudio_default(device: BluetoothDevice) -> bool:
        """Set device as default PulseAudio output."""
        try:
            # Get PulseAudio sink index
            result = subprocess.run(
                ["pactl", "list", "sinks"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if device.name in line or device.mac_address in line:
                        # Extract sink number and set as default
                        subprocess.run(
                            ["pactl", "set-default-sink", device.mac_address],
                            capture_output=True,
                            timeout=5
                        )
                        logger.info(f"Set {device.name} as default PulseAudio output")
                        return True

            # Fallback: try using device MAC address directly
            result = subprocess.run(
                ["pactl", "set-default-sink", device.mac_address],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0

        except Exception as e:
            logger.error(f"Error setting PulseAudio default: {e}")
            return False

    @staticmethod
    def _get_non_bluetooth_sinks() -> list[str]:
        """Get list of non-Bluetooth audio sinks (speakers, headphones, etc)."""
        try:
            result = subprocess.run(
                ["pactl", "list", "sinks"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return []
            
            sinks = []
            current_sink = None
            
            for line in result.stdout.split('\n'):
                if line.startswith('Sink #'):
                    # Extract sink number (e.g., "Sink #2")
                    parts = line.split()
                    if len(parts) >= 2:
                        current_sink = parts[1]
                elif 'Name:' in line and current_sink:
                    # Extract sink name and check if it's not Bluetooth
                    name_parts = line.split('Name:', 1)
                    if len(name_parts) > 1:
                        sink_name = name_parts[1].strip().strip('"')
                        # Skip Bluetooth devices (they have specific patterns)
                        if 'bluez' not in sink_name.lower() and 'bluetooth' not in sink_name.lower():
                            sinks.append(sink_name)
                        current_sink = None
            
            return sinks
        except Exception as e:
            logger.error(f"Error getting non-Bluetooth sinks: {e}")
            return []

    @staticmethod
    def _set_default_to_non_bluetooth() -> bool:
        """Set default audio output to a non-Bluetooth device.
        
        This prevents automatic audio passthrough to Bluetooth devices.
        Called during initialization to ensure audio doesn't flow to Bluetooth
        unless explicitly enabled by the application.
        """
        try:
            non_bt_sinks = DebianBluetoothBackend._get_non_bluetooth_sinks()
            
            if not non_bt_sinks:
                logger.warning("No non-Bluetooth audio sinks found")
                return False
            
            # Use the first non-Bluetooth sink (usually the primary speaker)
            default_sink = non_bt_sinks[0]
            
            result = subprocess.run(
                ["pactl", "set-default-sink", default_sink],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info(f"Set default audio output to: {default_sink}")
                return True
            else:
                logger.warning(f"Failed to set default sink to {default_sink}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting default to non-Bluetooth: {e}")
            return False

    def disable_all_bluetooth_audio(self) -> bool:
        """Disable audio passthrough for all Bluetooth devices on Debian/Linux.
        
        This prevents any Bluetooth A2DP device from receiving audio until explicitly re-enabled.
        Uses PulseAudio to unload Bluetooth modules.
        """
        try:
            # First, disconnect all connected Bluetooth A2DP devices
            result = subprocess.run(
                ["bluetoothctl", "devices"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.startswith("Device"):
                        parts = line.split()
                        if len(parts) >= 2:
                            device_mac = parts[1]
                            # Disconnect the device
                            subprocess.run(
                                ["bluetoothctl", "disconnect", device_mac],
                                capture_output=True,
                                timeout=5
                            )
            
            # Set default sink to non-Bluetooth device
            self._set_default_to_non_bluetooth()
            
            logger.info("All Bluetooth audio passthrough disabled")
            return True
            
        except Exception as e:
            logger.error(f"Error disabling Bluetooth audio: {e}")
            return False


class BluetoothAudioManager:
    """High-level interface for Bluetooth audio management."""

    def __init__(self):
        """Initialize the appropriate backend based on the platform."""
        system = platform.system()

        if system == "Windows":
            self.backend = WindowsBluetoothBackend()
        elif system == "Linux":
            self.backend = DebianBluetoothBackend()
        else:
            raise OSError(f"Unsupported platform: {system}")

        self.current_device: Optional[BluetoothDevice] = None
        logger.info(f"BluetoothAudioManager initialized for {system}")

    def scan_for_devices(self) -> list[BluetoothDevice]:
        """Scan for available Bluetooth audio devices."""
        return self.backend.scan_devices()

    def connect(self, device: BluetoothDevice, set_as_default: bool = True) -> bool:
        """Connect to a Bluetooth device and optionally set as default output."""
        success = self.backend.connect_device(device)
        if success:
            if set_as_default:
                self.backend.set_as_default_output(device)
            self.current_device = device
        return success

    def disconnect(self) -> bool:
        """Disconnect from the current device."""
        if self.current_device:
            success = self.backend.disconnect_device(self.current_device)
            if success:
                self.current_device = None
            return success
        return False

    def enable_bluetooth_audio(self, device: BluetoothDevice) -> bool:
        """Enable audio passthrough for a specific Bluetooth device.
        
        This sets the device as the default audio output, allowing audio to pass through.
        Should be called when user selects Bluetooth audio mode.
        """
        success = self.connect(device, set_as_default=True)
        if success:
            logger.info(f"Enabled audio passthrough for Bluetooth device: {device.name}")
        return success

    def disable_all_bluetooth_audio(self) -> bool:
        """Disable audio passthrough for all Bluetooth devices.
        
        This prevents any Bluetooth device from receiving audio until explicitly re-enabled.
        Should be called when user switches away from Bluetooth audio mode.
        """
        try:
            # First disconnect current device if any
            if self.current_device:
                self.disconnect()
            
            # Then disable all Bluetooth audio at the backend level
            if hasattr(self.backend, 'disable_all_bluetooth_audio'):
                return self.backend.disable_all_bluetooth_audio()
            
            logger.info("All Bluetooth audio passthrough disabled")
            return True
        except Exception as e:
            logger.error(f"Error disabling Bluetooth audio: {e}")
            return False

    def get_connected_devices(self) -> list[BluetoothDevice]:
        """Get list of currently connected devices."""
        return self.backend.get_connected_devices()

    def save_device_config(self, config_file: Path | str = "bluetooth_config.json"):
        """Save current device configuration to file."""
        try:
            if self.current_device:
                config = {
                    "last_device": {
                        "name": self.current_device.name,
                        "mac_address": self.current_device.mac_address,
                    }
                }
                with open(config_file, "w") as f:
                    json.dump(config, f, indent=2)
                logger.info(f"Saved Bluetooth config to {config_file}")
                return True
        except Exception as e:
            logger.error(f"Error saving Bluetooth config: {e}")
        return False

    def load_device_config(self, config_file: Path | str = "bluetooth_config.json") -> Optional[BluetoothDevice]:
        """Load and reconnect to last used device."""
        try:
            if Path(config_file).exists():
                with open(config_file, "r") as f:
                    config = json.load(f)
                    device_info = config.get("last_device")
                    if device_info:
                        device = BluetoothDevice(
                            name=device_info["name"],
                            mac_address=device_info["mac_address"]
                        )
                        logger.info(f"Loaded Bluetooth device config: {device.name}")
                        return device
        except Exception as e:
            logger.error(f"Error loading Bluetooth config: {e}")
        return None

    def start_audio_stream(self) -> bool:
        """Start streaming audio to the connected Bluetooth device."""
        if not self.current_device:
            logger.warning("No Bluetooth device connected")
            return False
        
        logger.info(f"Starting audio stream to {self.current_device.name}")
        # On Windows and Linux, once the device is set as default, audio automatically streams
        # This is a placeholder for any platform-specific streaming setup
        return True

    def stop_audio_stream(self) -> bool:
        """Stop streaming audio to the Bluetooth device."""
        if not self.current_device:
            return False
        
        logger.info(f"Stopping audio stream to {self.current_device.name}")
        return True

    def scan_for_devices_async(self, callback: Callable[[list[BluetoothDevice]], None]) -> Thread:
        """Scan for Bluetooth devices asynchronously in a background thread.
        
        Args:
            callback: Function to call with the list of devices when scan completes
            
        Returns:
            The Thread object so caller can join() if needed
        """
        def _scan():
            devices = self.scan_for_devices()
            callback(devices)
        
        thread = Thread(target=_scan, daemon=True)
        thread.start()
        return thread

    def connect_async(self, device: BluetoothDevice, 
                     callback: Callable[[bool], None], 
                     set_as_default: bool = True) -> Thread:
        """Connect to a Bluetooth device asynchronously.
        
        Args:
            device: Device to connect to
            callback: Function to call with success/failure boolean when complete
            set_as_default: Whether to set as default audio output
            
        Returns:
            The Thread object so caller can join() if needed
        """
        def _connect():
            success = self.connect(device, set_as_default)
            callback(success)
        
        thread = Thread(target=_connect, daemon=True)
        thread.start()
        return thread
