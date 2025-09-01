"""
Muse Stream Client
Clean, modular client for streaming Muse device data
"""

import asyncio
from bleak import BleakClient, BleakScanner
import datetime
from typing import Optional, Callable, Dict, Any, List
import os
import logging

from .muse_decoder import MuseRealtimeDecoder, DecodedData

logger = logging.getLogger(__name__)


class MuseDeviceScanner:
    """Handles device discovery and connection"""

    @staticmethod
    async def find_device(name_filter: str = "Muse") -> Optional[Any]:
        """Find Muse device"""
        logger.info("Scanning for Muse devices...")
        devices = await BleakScanner.discover(timeout=5.0)

        for device in devices:
            if device.name and name_filter in device.name:
                logger.info(f"Found: {device.name} ({device.address})")
                return device

        return None

    @staticmethod
    def detect_device_model(device_name: str) -> str:
        """Detect device model from name"""
        if device_name and 'MuseS-' in device_name:
            return 'gen1'
        elif device_name and 'Muse-' in device_name:
            return 'gen3'
        else:
            return 'gen3'


class MuseDataCallbacks:
    """Manages data callbacks"""

    def __init__(self):
        self.callbacks: Dict[str, List[Callable]] = {
            'eeg': [],
            'ppg': [],
            'imu': [],
            'heart_rate': [],
            'packet': []
        }

    def register(self, data_type: str, callback: Callable):
        """Register a callback"""
        if data_type in self.callbacks:
            self.callbacks[data_type].append(callback)

    def trigger_eeg(self, data: Dict[str, Any]):
        """Trigger EEG callbacks"""
        for callback in self.callbacks['eeg']:
            if callback:
                callback(data)

    def trigger_ppg(self, data: Dict[str, Any]):
        """Trigger PPG callbacks"""
        for callback in self.callbacks['ppg']:
            if callback:
                callback(data)

    def trigger_imu(self, data: Dict[str, Any]):
        """Trigger IMU callbacks"""
        for callback in self.callbacks['imu']:
            if callback:
                callback(data)

    def trigger_heart_rate(self, hr: float):
        """Trigger heart rate callbacks"""
        for callback in self.callbacks['heart_rate']:
            if callback:
                callback(hr)

    def trigger_packet(self, packet: bytes):
        """Trigger packet callbacks"""
        for callback in self.callbacks['packet']:
            if callback:
                callback(packet)


class MuseStreamClient:
    """
    Modern Muse S client with real-time processing

    Features:
    - Real-time decoding with callbacks
    - Simple API for researchers
    - Automatic device detection
    - Support for multiple Muse device generations
    """

    def __init__(self,
                 device_model: str = "auto",
                 verbose: bool = True):
        """
        Initialize streaming client

        Args:
            device_model: Device model ('auto', 'gen1', 'gen3')
            verbose: Print status messages
        """
        self.device_model = device_model
        self.verbose = verbose

        # Components
        self.decoder = MuseRealtimeDecoder(device_model)
        self.callbacks = MuseDataCallbacks()
        self.scanner = MuseDeviceScanner()

        # BLE client
        self.client: Optional[BleakClient] = None

        # Session info
        self.session_start = None
        self.is_streaming = False
        self.packet_count = 0
        self.device_info = {}

    def on_eeg(self, callback: Callable[[Dict[str, Any]], None]):
        """Register EEG callback"""
        self.callbacks.register('eeg', callback)
        self.decoder.register_callback('eeg',
            lambda data: callback({'channels': data.eeg, 'timestamp': data.timestamp}))

    def on_ppg(self, callback: Callable[[Dict[str, Any]], None]):
        """Register PPG callback"""
        self.callbacks.register('ppg', callback)
        self.decoder.register_callback('ppg',
            lambda data: callback({'samples': data.ppg.get('samples', []) if data.ppg else [], 'timestamp': data.timestamp}))

    def on_heart_rate(self, callback: Callable[[float], None]):
        """Register heart rate callback"""
        self.callbacks.register('heart_rate', callback)
        self.decoder.register_callback('heart_rate',
            lambda data: callback(data.heart_rate) if data.heart_rate else None)

    def on_imu(self, callback: Callable[[Dict[str, Any]], None]):
        """Register IMU callback"""
        self.callbacks.register('imu', callback)
        self.decoder.register_callback('imu',
            lambda data: callback({'accel': data.imu.get('accel') if data.imu else None, 'gyro': data.imu.get('gyro') if data.imu else None}))

    def on_packet(self, callback: Callable[[bytes], None]):
        """Register raw packet callback"""
        self.callbacks.register('packet', callback)

    def log(self, message: str, level: str = "INFO"):
        """Log message with timestamp"""
        if self.verbose:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] {message}")

    async def find_device(self) -> Optional[Any]:
        """
        Find Muse device by scanning for BLE devices

        Returns:
            Device object if found, None otherwise
        """
        return await self.scanner.find_device()

    def _handle_sensor_notification(self, sender, data: bytearray):
        """Handle incoming sensor data"""
        self.packet_count += 1
        timestamp = datetime.datetime.now()

        # First packet - streaming confirmed
        if not self.is_streaming:
            self.is_streaming = True
            self.session_start = timestamp
            self.log("Streaming started!")

        # Decode packet - use characteristic-specific decoding for Gen1
        char_uuid = str(sender.uuid) if hasattr(sender, 'uuid') else None
        if char_uuid and 'Gen 1' in self.decoder.config.get('name', ''):
            # Gen1: Use characteristic-specific decoding
            decoded = self.decoder.decode_raw_packet(bytes(data), char_uuid, timestamp)
        else:
            # Gen3 or unknown: Use standard decoding
            decoded = self.decoder.decode(bytes(data), timestamp)

        # Trigger callbacks
        if decoded.eeg:
            self.callbacks.trigger_eeg({'channels': decoded.eeg, 'timestamp': decoded.timestamp})

        if decoded.ppg:
            self.callbacks.trigger_ppg({'samples': decoded.ppg.get('samples', []), 'timestamp': decoded.timestamp})

        if decoded.imu:
            self.callbacks.trigger_imu({'accel': decoded.imu.get('accel'), 'gyro': decoded.imu.get('gyro'), 'timestamp': decoded.timestamp})

        if decoded.heart_rate:
            self.callbacks.trigger_heart_rate(decoded.heart_rate)

        # Raw packet callback
        self.callbacks.trigger_packet(bytes(data))

        # Status update
        if self.packet_count % 100 == 0:
            self.log(f"Packets: {self.packet_count}")
            if decoded.heart_rate:
                self.log(f"Heart Rate: {decoded.heart_rate:.0f} BPM")

    def _handle_control_notification(self, sender, data: bytearray):
        """Handle control responses"""
        try:
            text = data.decode('utf-8', errors='ignore')
            if '{' in text and '}' in text:
                start = text.index('{')
                end = text.rindex('}') + 1
                json_str = text[start:end]

                import json
                info = json.loads(json_str)
                self.device_info.update(info)

                if self.verbose:
                    if 'fw' in info:
                        self.log(f"Firmware: {info['fw']}")
                    if 'bp' in info:
                        self.log(f"Battery: {info['bp']}%")
        except:
            pass

    async def connect_and_stream(self,
                                  address: str,
                                  duration_seconds: int = 30) -> bool:
        """
        Connect and stream data

        Args:
            address: Device MAC address
            duration_seconds: Streaming duration (0 for continuous)

        Returns:
            Success status
        """
        try:
            self.log(f"Connecting to {address}...")

            async with BleakClient(address) as client:
                self.client = client
                self.log("Connected!")

                # Enable notifications
                await client.start_notify(
                    "273e0001-4c4d-454d-96be-f03bac821358",
                    self._handle_control_notification
                )

                # Enable sensor notifications - handle Gen1 vs Gen3 differently
                enabled_count = 0

                # Get device config to determine which characteristics to enable
                from muse_config import get_device_config
                device_config = get_device_config(self.device_model)

                # For Gen1 devices, enable ALL sensor characteristics
                if 'Gen 1' in device_config.get('name', ''):
                    # Gen1: Enable ALL sensor characteristics
                    for char_uuid in device_config['sensor_char_uuids']:
                        try:
                            await client.start_notify(char_uuid, self._handle_sensor_notification)
                            enabled_count += 1
                            self.log(f"Sensor notifications enabled ({char_uuid[-4:]})")
                        except Exception as e:
                            self.log(f"Failed to enable {char_uuid[-4:]}: {e}")
                            continue
                else:
                    # Gen3: Try the first one that works
                    for char_uuid in device_config['sensor_char_uuids']:
                        try:
                            await client.start_notify(char_uuid, self._handle_sensor_notification)
                            enabled_count += 1
                            self.log(f"Sensor notifications enabled ({char_uuid[-4:]})")
                            break
                        except Exception as e:
                            self.log(f"Failed to enable {char_uuid[-4:]}: {e}")
                            continue

                if enabled_count == 0:
                    self.log("Failed to enable any sensor notifications")
                    return False

                self.log(f"Successfully enabled {enabled_count} sensor notification(s)")

                # Get device info
                await client.write_gatt_char(
                    "273e0001-4c4d-454d-96be-f03bac821358",
                    b'\x03v6\n',
                    response=False
                )
                await asyncio.sleep(0.1)

                # Start streaming
                self.log("Starting stream...")
                await client.write_gatt_char(
                    "273e0001-4c4d-454d-96be-f03bac821358",
                    b'\x06dc001\n',
                    response=False
                )
                await asyncio.sleep(0.05)
                await client.write_gatt_char(
                    "273e0001-4c4d-454d-96be-f03bac821358",
                    b'\x06dc001\n',
                    response=False
                )

                # Wait for streaming to start
                await asyncio.sleep(2)

                if not self.is_streaming:
                    self.log("Streaming failed to start")
                    return False

                # Stream for specified duration
                if duration_seconds > 0:
                    self.log(f"Streaming for {duration_seconds} seconds...")
                    await asyncio.sleep(duration_seconds)
                else:
                    self.log("Streaming continuously (Ctrl+C to stop)...")
                    while True:
                        await asyncio.sleep(1)

                # Stop streaming
                self.log("Stopping stream...")
                await client.write_gatt_char(
                    "273e0001-4c4d-454d-96be-f03bac821358",
                    b'\x026h\n',
                    response=False
                )

                return True

        except asyncio.CancelledError:
            self.log("Streaming cancelled")
            return False
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            self.log(f"Error: {e}")
            return False

        finally:
            self.client = None

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        stats = self.decoder.get_stats()
        stats.update({
            'packets_received': self.packet_count,
            'session_start': self.session_start,
            'device_info': self.device_info
        })
        return stats

    def reset_stats(self):
        """Reset statistics"""
        self.decoder.reset_stats()
        self.packet_count = 0
        self.session_start = None
        self.is_streaming = False
        self.device_info = {}


# Convenience functions
async def stream_device(duration_seconds: int = 30, device_model: str = 'auto'):
    """
    Stream data from Muse device

    Args:
        duration_seconds: How long to stream
        device_model: Device model ('auto', 'gen1', 'gen3')
    """
    client = MuseStreamClient(device_model=device_model)

    # Find device
    device = await client.find_device()
    if not device:
        print("No Muse device found")
        return None

    # Stream
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration_seconds
    )

    if success:
        stats = client.get_stats()
        print(f"\nSession complete!")
        print(f"Packets: {stats['packets_received']}")
        if 'last_heart_rate' in stats and stats['last_heart_rate']:
            print(f"Last heart rate: {stats['last_heart_rate']:.0f} BPM")
        return stats

    return None
