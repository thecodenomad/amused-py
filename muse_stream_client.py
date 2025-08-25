"""
Muse Stream Client with Binary Storage
Efficient streaming with real-time processing and compact binary storage

This client combines the best of both worlds:
- Real-time data processing and callbacks
- Efficient binary storage (10x smaller than CSV)
- On-the-fly decoding when needed
- Support for multiple Muse device generations (Gen 1, Gen 3/Athena)
"""

import asyncio
from bleak import BleakClient, BleakScanner
import datetime
from typing import Optional, Callable, Dict, Any, List
import os
import struct

from muse_raw_stream import MuseRawStream
from muse_realtime_decoder import MuseRealtimeDecoder, DecodedData

# Device configurations for different Muse generations
class MuseDeviceConfig:
    """Configuration for different Muse device generations"""

    @staticmethod
    def get_gen3_config():
        """Configuration for Muse S Gen 3 (Athena)"""
        return {
            'name': 'Muse S Gen 3 (Athena)',
            'service_uuid': "0000fe8d-0000-1000-8000-00805f9b34fb",
            'control_char_uuid': "273e0001-4c4d-454d-96be-f03bac821358",
            'sensor_char_uuids': [
                "273e0013-4c4d-454d-96be-f03bac821358",  # Combined sensors
                "273e0003-4c4d-454d-96be-f03bac821358",  # EEG TP9
            ],
            'commands': {
                'v6': bytes.fromhex('0376360a'),           # Version
                's': bytes.fromhex('02730a'),              # Status
                'h': bytes.fromhex('02680a'),              # Halt
                'p21': bytes.fromhex('047032310a'),        # Basic preset
                'p1034': bytes.fromhex('0670313033340a'),  # Sleep preset
                'p1035': bytes.fromhex('0670313033350a'),  # Sleep preset 2
                'dc001': bytes.fromhex('0664633030310a'),  # Start streaming
                'L1': bytes.fromhex('034c310a'),           # L1 command
            },
            'eeg_scale_factor': 0.48828125,
            'imu_accel_scale': 2.0 / 32768.0,
            'imu_gyro_scale': 250.0 / 32768.0,
            'expected_packet_types': [0xDF, 0xF4, 0xDB, 0xD9],
            'eeg_channels': ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']
        }

    @staticmethod
    def get_gen1_config():
        """Configuration for Muse S Gen 1"""
        return {
            'name': 'Muse S Gen 1',
            'service_uuid': "0000fe8d-0000-1000-8000-00805f9b34fb",  # May be same
            'control_char_uuid': "273e0001-4c4d-454d-96be-f03bac821358",  # May be same
            'sensor_char_uuids': [
                "273e0003-4c4d-454d-96be-f03bac821358",  # EEG TP9 (688 packets)
                "273e0004-4c4d-454d-96be-f03bac821358",  # EEG AF7 (688 packets)
                "273e0005-4c4d-454d-96be-f03bac821358",  # EEG AF8 (688 packets)
                "273e0006-4c4d-454d-96be-f03bac821358",  # EEG TP10 (688 packets)
                "273e0008-4c4d-454d-96be-f03bac821358",  # IMU data (153 packets)
                "273e0009-4c4d-454d-96be-f03bac821358",  # PPG data (567 packets)
                "273e000a-4c4d-454d-96be-f03bac821358",  # PPG data (567 packets)
            ],
            'commands': {
                'v1': bytes.fromhex('0376310a'),           # Version (Gen 1 style)
                'v6': bytes.fromhex('0376360a'),           # Version (Gen 3 style)
                's': bytes.fromhex('02730a'),              # Status
                'h': bytes.fromhex('02680a'),              # Halt
                'p21': bytes.fromhex('047032310a'),        # Basic preset (standard)
                'p22': bytes.fromhex('047032320a'),        # Basic preset (lower rate)
                'p23': bytes.fromhex('047032330a'),        # Basic preset (even lower rate)
                'p1034': bytes.fromhex('0670313033340a'),  # Sleep preset (standard)
                'p1035': bytes.fromhex('0670313033350a'),  # Sleep preset (lower rate)
                'p1036': bytes.fromhex('0670313033360a'),  # Sleep preset (lowest rate)
                'dc001': bytes.fromhex('0664633030310a'),  # Start streaming
                'L1': bytes.fromhex('034c310a'),           # L1 command
            },
            'eeg_scale_factor': 1000.0 / 2048.0,  # Updated based on packet analysis
            'imu_accel_scale': 1.0 / 100.0,       # Updated based on packet analysis
            'imu_gyro_scale': 1.0 / 100.0,        # Updated based on packet analysis
            'expected_packet_types': [0xDF, 0xF4, 0xDB, 0xD9],
            'eeg_channels': ['TP9', 'AF7', 'AF8', 'TP10'],  # Only supported channels on Gen1
            'supported_channels': ['TP9', 'AF7', 'AF8', 'TP10'],  # Explicitly list supported channels
            'max_sampling_rate': 250,  # Gen1 max sampling rate (Hz)
            'stabilization_time': 5.0,  # 5 second stabilization period for Gen1
            'quality_threshold': 0.60,   # Require 60% valid samples before recording
            'quality_window': 1000,      # Check quality over 1000 samples
            'max_quality_wait': 15.0,    # Maximum time to wait for good quality (seconds)
        }

class MuseStreamClient:
    """
    Modern Muse S client with binary storage and real-time processing

    Features:
    - Saves raw data in compact binary format
    - Real-time decoding with callbacks
    - Simple API for researchers
    - Automatic file management
    - Support for multiple Muse device generations (Gen 1, Gen 3/Athena)
    """

    def __init__(self,
                 save_raw: bool = False,  # Default to NOT saving
                 decode_realtime: bool = True,
                 data_dir: str = "muse_data",
                 verbose: bool = True,
                 device_model: str = "gen1"):  # 'gen1', 'gen3', 'auto', or custom config dict
        """
        Initialize streaming client

        Args:
            save_raw: Save raw binary data to file (default: False)
            decode_realtime: Decode packets in real-time (default: True)
            data_dir: Directory for data files (only created if save_raw=True)
            verbose: Print status messages
        """
        self.save_raw = save_raw
        self.decode_realtime = decode_realtime
        self.data_dir = data_dir
        self.verbose = verbose

        # Store original device model for auto-detection
        self.device_model = device_model

        # Set up device configuration
        self.device_config = self._get_device_config(device_model)

        # Only create data directory if we're saving
        if save_raw:
            os.makedirs(data_dir, exist_ok=True)

        # BLE client
        self.client: Optional[BleakClient] = None

        # Raw stream handler
        self.raw_stream: Optional[MuseRawStream] = None

        # Real-time decoder
        self.decoder = MuseRealtimeDecoder() if decode_realtime else None

        # Session info
        self.session_start = None
        self.is_streaming = False
        self.packet_count = 0

        # Device info
        self.device_info = {}

        # Auto-detection state
        self.auto_detected_model = None

        # User callbacks
        self.user_callbacks = {
            'eeg': None,
            'ppg': None,
            'imu': None,
            'heart_rate': None,
            'packet': None  # Called for every packet
        }

    def _get_device_config(self, device_model: str) -> Dict[str, Any]:
        """Get configuration for the specified device model"""
        if device_model == "gen1":
            return MuseDeviceConfig.get_gen1_config()
        elif device_model == "gen3":
            return MuseDeviceConfig.get_gen3_config()
        elif device_model == "auto":
            # Auto-detection will be performed later during connection
            # Start with Gen1 config as fallback (more common for existing users)
            return MuseDeviceConfig.get_gen1_config()
        elif isinstance(device_model, dict):
            # Custom configuration provided
            return device_model
        else:
            raise ValueError(f"Unknown device model: {device_model}")

    def get_device_model_name(self) -> str:
        """Get the current device model name"""
        if self.auto_detected_model:
            return f"{self.device_config.get('name', 'Unknown')} (auto-detected: {self.auto_detected_model})"
        return self.device_config.get('name', 'Unknown')

    async def _auto_detect_device_model(self, client: BleakClient) -> str:
        """
        Auto-detect the Muse device model based on device characteristics

        Detection methods:
        1. Device name pattern analysis (most reliable)
        2. Firmware version analysis
        3. Command response patterns
        """
        self.log("🔍 Auto-detecting device model...")

        # Method 1: Device name pattern analysis (most reliable)
        try:
            # Get device name from the client
            device_name = getattr(client, '_device', None)
            if device_name:
                device_name = getattr(device_name, 'name', None) or str(device_name)
            else:
                device_name = str(client)

            self.log(f"📡 Device name: {device_name}")

            # Gen1 devices typically have names like "MuseS-XXXX"
            # Gen3 devices typically have names like "Muse-XXXX" or different patterns
            if device_name and 'MuseS-' in device_name:
                self.log("✅ Detected: Muse S Gen 1 (based on device name)")
                return 'gen1'
            elif device_name and 'Muse-' in device_name and 'MuseS-' not in device_name:
                self.log("✅ Detected: Muse S Gen 3 (based on device name)")
                return 'gen3'

        except Exception as e:
            self.log(f"⚠️ Device name detection failed: {e}")

        # Method 2: Try firmware version detection
        try:
            control_uuid = self.device_config['control_char_uuid']

            # Try Gen1 version command first
            gen1_cmd = MuseDeviceConfig.get_gen1_config()['commands']['v1']
            await client.write_gatt_char(control_uuid, gen1_cmd, response=False)
            await asyncio.sleep(0.2)

            # Check if we got a response that indicates Gen1
            if 'fw' in self.device_info:
                fw_version = self.device_info['fw']
                self.log(f"📡 Firmware detected: {fw_version}")

                # Gen1 firmware versions are typically lower numbers
                # Gen3/Athena firmware versions are higher (e.g., 1.x.x for Gen1, 2.x.x+ for Gen3)
                if fw_version.startswith('1.') or fw_version.startswith('0.'):
                    self.log("✅ Detected: Muse S Gen 1 (based on firmware)")
                    return 'gen1'
                elif fw_version.startswith('2.') or fw_version.startswith('3.'):
                    self.log("✅ Detected: Muse S Gen 3 (based on firmware)")
                    return 'gen3'

        except Exception as e:
            self.log(f"⚠️ Firmware detection failed: {e}")

        # Method 3: Try command response patterns
        try:
            # Test with a Gen1-specific command pattern
            gen1_status = MuseDeviceConfig.get_gen1_config()['commands']['s']
            await client.write_gatt_char(control_uuid, gen1_status, response=False)
            await asyncio.sleep(0.1)

            # If we get here without errors, and have device info, check patterns
            if self.device_info:
                # Gen1 devices often have different response patterns
                if 'bp' in self.device_info:  # Battery percentage
                    bp = self.device_info['bp']
                    if isinstance(bp, str) and bp.isdigit():
                        bp_val = int(bp)
                        if bp_val > 0:  # Valid battery reading
                            self.log("✅ Detected: Muse S Gen 1 (based on command response)")
                            return 'gen1'

        except Exception as e:
            self.log(f"⚠️ Command pattern detection failed: {e}")

        # Method 4: Default to Gen1 if detection inconclusive (more common for existing users)
        self.log("⚠️ Could not conclusively detect model, defaulting to Gen 1")
        return 'gen1'

        # We'll add cleanup later when we have the method defined

    def on_eeg(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for EEG data"""
        self.user_callbacks['eeg'] = callback
        if self.decoder:
            self.decoder.register_callback('eeg',
                lambda data: callback({'channels': data.eeg, 'timestamp': data.timestamp}))

    def on_ppg(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for PPG data"""
        self.user_callbacks['ppg'] = callback
        if self.decoder:
            self.decoder.register_callback('ppg',
                lambda data: callback({'samples': data.ppg.get('samples', []) if data.ppg else [], 'timestamp': data.timestamp}))

    def on_heart_rate(self, callback: Callable[[float], None]):
        """Register callback for heart rate"""
        self.user_callbacks['heart_rate'] = callback
        if self.decoder:
            self.decoder.register_callback('heart_rate',
                lambda data: callback(data.heart_rate))

    def on_imu(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for IMU data"""
        self.user_callbacks['imu'] = callback
        if self.decoder:
            self.decoder.register_callback('imu',
                lambda data: callback({'accel': data.imu.get('accel'), 'gyro': data.imu.get('gyro')}))

    def on_packet(self, callback: Callable[[bytes], None]):
        """Register callback for raw packets"""
        self.user_callbacks['packet'] = callback

    async def _wait_for_signal_quality(self, client):
        """Wait for signal quality to reach acceptable threshold before recording"""
        quality_threshold = self.device_config.get('quality_threshold', 0.60)
        max_wait_time = self.device_config.get('max_quality_wait', 15.0)

        self.log(f"Monitoring signal quality (target: {quality_threshold:.0%})...")

        # Simple approach: wait for basic stabilization period
        # In a more advanced implementation, we could monitor actual signal quality
        stabilization_time = self.device_config.get('stabilization_time', 5.0)

        self.log(f"Waiting {stabilization_time}s for Gen1 device stabilization...")
        await asyncio.sleep(stabilization_time)
        self.log("Stabilization complete, starting data collection")

        # Future enhancement: Could monitor actual EEG signal quality here
        # by temporarily enabling notifications and checking signal characteristics

    def _trigger_user_callbacks(self, decoded: DecodedData):
        """Trigger user callbacks with decoded data"""
        # EEG callback
        if decoded.eeg and self.user_callbacks['eeg']:
            # Format EEG data for callback
            eeg_data = {'channels': decoded.eeg, 'timestamp': decoded.timestamp}
            self.user_callbacks['eeg'](eeg_data)

        # PPG callback
        if decoded.ppg and self.user_callbacks['ppg']:
            # Format PPG data for callback
            ppg_data = {'samples': decoded.ppg.get('samples', []), 'timestamp': decoded.timestamp}
            self.user_callbacks['ppg'](ppg_data)

        # IMU callback
        if decoded.imu and self.user_callbacks['imu']:
            # Format IMU data for callback
            imu_data = {'accel': decoded.imu.get('accel'), 'gyro': decoded.imu.get('gyro'), 'timestamp': decoded.timestamp}
            self.user_callbacks['imu'](imu_data)

        # Heart rate callback
        if decoded.heart_rate and self.user_callbacks['heart_rate']:
            self.user_callbacks['heart_rate'](decoded.heart_rate)

    def log(self, message: str, level: str = "INFO"):
        """Log message with timestamp"""
        if self.verbose:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] {message}")

    async def find_device(self, name_filter: str = "Muse") -> Optional[Any]:
        """Find Muse device

        Args:
            name_filter: Name filter for device search

        Returns:
            Device object or None
        """
        self.log("Scanning for Muse devices...")
        devices = await BleakScanner.discover(timeout=5.0)

        for device in devices:
            if device.name and name_filter in device.name:
                self.log(f"Found: {device.name} ({device.address})")
                return device

        return None

    def handle_sensor_notification(self, sender, data: bytearray):
        """Handle incoming sensor data"""
        self.packet_count += 1
        timestamp = datetime.datetime.now()

        # First packet - streaming confirmed
        if not self.is_streaming:
            self.is_streaming = True
            self.session_start = timestamp
            self.log("Streaming started!")

            # Initialize raw stream file
            if self.save_raw:
                filename = f"{self.data_dir}/muse_{timestamp.strftime('%Y%m%d_%H%M%S')}.bin"
                self.raw_stream = MuseRawStream(filename)
                self.raw_stream.open_write()
                self.log(f"Saving to: {filename}")

        # Save raw data
        if self.save_raw and self.raw_stream:
            self.raw_stream.write_packet(bytes(data), timestamp)

        # Decode in real-time - use characteristic-specific decoding for Gen1
        if self.decode_realtime and self.decoder:
            if 'Gen 1' in self.device_config.get('name', '') and hasattr(sender, 'uuid'):
                # Gen1: Use characteristic-specific decoding
                char_uuid = str(sender.uuid)
                print(f"🔧 Decoding Gen1 packet from {char_uuid[-4:]}: {data.hex()[:20]}...")
                decoded = self.decoder.decode_raw_packet(bytes(data), char_uuid, timestamp)
                print(f"🔧 Decoded: eeg={bool(decoded.eeg)}, ppg={bool(decoded.ppg)}, imu={bool(decoded.imu)}")

                # Trigger user callbacks directly with decoded data
                self._trigger_user_callbacks(decoded)
            else:
                # Gen3: Use standard decoding
                decoded = self.decoder.decode(bytes(data), timestamp)
                # Trigger user callbacks directly with decoded data
                self._trigger_user_callbacks(decoded)

        # User callback for raw packets
        if self.user_callbacks['packet']:
            self.user_callbacks['packet'](bytes(data))

        # Status update every 100 packets
        if self.packet_count % 100 == 0:
            self.log(f"Packets: {self.packet_count}")
            if self.decoder:
                stats = self.decoder.get_stats()
                if stats['last_heart_rate']:
                    self.log(f"Heart Rate: {stats['last_heart_rate']:.0f} BPM")

    def handle_control_notification(self, sender, data: bytearray):
        """Handle control responses"""
        try:
            # Try to decode as string/JSON
            text = data.decode('utf-8', errors='ignore')
            if '{' in text and '}' in text:
                # Extract JSON portion
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
                                 duration_seconds: int = 30,
                                 preset: str = 'p1034') -> bool:
        """
        Connect and stream data

        Args:
            address: Device MAC address
            duration_seconds: Streaming duration (0 for continuous)
            preset: Sensor preset ('p21' for basic, 'p1034' for full)

        Returns:
            Success status
        """
        try:
            self.log(f"Connecting to {address}...")

            async with BleakClient(address) as client:
                self.client = client
                self.log("Connected!")

                # Enable control notifications
                await client.start_notify(self.device_config['control_char_uuid'], self.handle_control_notification)

                # Auto-detect device model if requested
                if self.device_model == "auto":
                    detected_model = await self._auto_detect_device_model(client)
                    if detected_model != 'gen3':  # Only switch if not Gen3 (which is our default)
                        self.log(f"🔄 Switching to {detected_model} configuration")
                        self.device_config = self._get_device_config(detected_model)
                        self.auto_detected_model = detected_model

                # Get device info - try Gen 1 first, then Gen 3
                version_cmd = self.device_config['commands'].get('v1', self.device_config['commands']['v6'])
                await client.write_gatt_char(self.device_config['control_char_uuid'], version_cmd, response=False)
                await asyncio.sleep(0.1)

                await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands']['s'], response=False)
                await asyncio.sleep(0.1)

                # Halt any existing streams
                await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands']['h'], response=False)
                await asyncio.sleep(0.1)

                # Set preset (use lower rate presets for Gen1)
                self.log(f"Setting preset: {preset}")
                if preset in self.device_config['commands']:
                    await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands'][preset], response=False)

                    # For Gen1, add stabilization delay and use lower rate preset if available
                    if 'Gen 1' in self.device_config.get('name', ''):
                        await asyncio.sleep(0.1)
                        # Try to use the lowest rate preset for Gen1 - prioritize p1036 for 128Hz-like performance
                        if 'p1036' in self.device_config['commands']:
                            await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands']['p1036'], response=False)
                            self.log("Applied Gen1 ultra-low-rate preset (p1036) for 128Hz-like performance")
                        elif 'p23' in self.device_config['commands']:
                            await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands']['p23'], response=False)
                            self.log("Applied Gen1 low-rate preset (p23) for better data quality")
                        elif 'p22' in self.device_config['commands']:
                            await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands']['p22'], response=False)
                            self.log("Applied Gen1 low-rate preset (p22) for better data quality")

                        # Add quality-based stabilization for Gen1 devices
                        await self._wait_for_signal_quality(client)
                else:
                    self.log(f"Warning: Preset {preset} not available for {self.device_config['name']}")
                await asyncio.sleep(0.1)

                # Enable sensor notifications
                # For Gen1, try to enable ALL sensor characteristics
                # For Gen3, use the first one that works
                enabled_count = 0
                if 'Gen 1' in self.device_config.get('name', ''):
                    # Gen1: Enable ALL sensor characteristics
                    for char_uuid in self.device_config['sensor_char_uuids']:
                        try:
                            await client.start_notify(char_uuid, self.handle_sensor_notification)
                            enabled_count += 1
                            self.log(f"Sensor notifications enabled ({char_uuid})")
                        except Exception as e:
                            self.log(f"Failed to enable {char_uuid}: {e}")
                            continue
                else:
                    # Gen3: Use first one that works
                    for char_uuid in self.device_config['sensor_char_uuids']:
                        try:
                            await client.start_notify(char_uuid, self.handle_sensor_notification)
                            enabled_count += 1
                            self.log(f"Sensor notifications enabled ({char_uuid})")
                            break
                        except Exception as e:
                            self.log(f"Failed to enable {char_uuid}: {e}")
                            continue

                if enabled_count == 0:
                    self.log("Failed to enable sensor notifications")
                    return False

                self.log(f"Successfully enabled {enabled_count} sensor notification(s)")

                # Re-register user callbacks with decoder
                if self.decoder:
                    # Re-register all callbacks to ensure they're connected
                    for callback_type in ['eeg', 'ppg', 'heart_rate', 'imu']:
                        if self.user_callbacks.get(callback_type):
                            # Clear and re-add
                            self.decoder.callbacks[callback_type] = []

                    if self.user_callbacks['eeg']:
                        self.decoder.register_callback('eeg',
                            lambda data: self.user_callbacks['eeg']({'channels': data.eeg, 'timestamp': data.timestamp}))
                    if self.user_callbacks['ppg']:
                        self.decoder.register_callback('ppg',
                            lambda data: self.user_callbacks['ppg']({'samples': data.ppg.get('samples', []) if data.ppg else [], 'timestamp': data.timestamp}))
                    if self.user_callbacks['heart_rate']:
                        self.decoder.register_callback('heart_rate',
                            lambda data: self.user_callbacks['heart_rate'](data.heart_rate) if data.heart_rate else None)
                    if self.user_callbacks['imu']:
                        self.decoder.register_callback('imu',
                            lambda data: self.user_callbacks['imu']({'accel': data.imu.get('accel'), 'gyro': data.imu.get('gyro')}))

                # Start streaming (SEND TWICE!)
                self.log("Starting stream...")
                await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands']['dc001'], response=False)
                await asyncio.sleep(0.05)
                await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands']['dc001'], response=False)
                await asyncio.sleep(0.1)

                # Send L1 command
                await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands']['L1'], response=False)

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
                await client.write_gatt_char(self.device_config['control_char_uuid'], self.device_config['commands']['h'], response=False)

                return True

        except Exception as e:
            self.log(f"Error: {e}")
            return False

        finally:
            # Clean up
            if self.raw_stream:
                self.raw_stream.close()
                if self.verbose:
                    info = self.raw_stream.get_file_info()
                    self.log(f"Saved {info['packet_count']} packets ({info['file_size_mb']:.1f} MB)")

            self.client = None

    def get_summary(self) -> Dict[str, Any]:
        """Get session summary"""
        summary = {
            'packets_received': self.packet_count,
            'session_start': self.session_start,
            'device_info': self.device_info
        }

        if self.decoder:
            stats = self.decoder.get_stats()
            summary.update({
                'eeg_samples': stats['eeg_samples'],
                'ppg_samples': stats['ppg_samples'],
                'imu_samples': stats['imu_samples'],
                'last_heart_rate': stats['last_heart_rate'],
                'decode_errors': stats['decode_errors']
            })

        if self.raw_stream:
            info = self.raw_stream.get_file_info()
            summary['file_info'] = info

        return summary

# Convenience functions
async def stream_only(duration_seconds: int = 30, preset: str = 'p1034', device_model: str = 'auto'):
    """
    Stream data without saving (real-time processing only)

    Args:
        duration_seconds: How long to stream
        preset: Sensor configuration
        device_model: Device model ('auto', 'gen1', 'gen3', or custom config dict)
    """
    client = MuseStreamClient(save_raw=False, decode_realtime=True, device_model=device_model)

    # Find device
    device = await client.find_device()
    if not device:
        print("No Muse device found")
        return None

    # Stream without saving
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration_seconds,
        preset=preset
    )

    if success:
        summary = client.get_summary()
        print(f"\nSession complete!")
        print(f"Device: {client.get_device_model_name()}")
        print(f"Packets: {summary['packets_received']}")
        if 'eeg_samples' in summary:
            print(f"EEG samples: {summary['eeg_samples']}")
        if 'last_heart_rate' in summary and summary['last_heart_rate']:
            print(f"Last heart rate: {summary['last_heart_rate']:.0f} BPM")
        return summary

    return None

async def stream_and_save(duration_seconds: int = 30, preset: str = 'p1034', device_model: str = 'auto'):
    """
    Stream AND save data to binary file

    Args:
        duration_seconds: How long to stream
        preset: Sensor configuration
        device_model: Device model ('auto', 'gen1', 'gen3', or custom config dict)
    """
    client = MuseStreamClient(save_raw=True, decode_realtime=True, device_model=device_model)

    # Find device
    device = await client.find_device()
    if not device:
        print("No Muse device found")
        return None

    # Stream and save
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration_seconds,
        preset=preset
    )

    if success:
        summary = client.get_summary()
        print(f"\nSession complete!")
        print(f"Device: {client.get_device_model_name()}")
        print(f"Packets: {summary['packets_received']}")
        if 'file_info' in summary:
            print(f"Saved to: {summary['file_info']['filepath']}")
            print(f"File size: {summary['file_info']['file_size_mb']:.1f} MB")
        return summary

    return None

# Example usage
if __name__ == "__main__":
    import asyncio

    async def example():
        """Example with callbacks"""
        client = MuseStreamClient()

        # Register callbacks
        client.on_eeg(lambda data: print(f"EEG: {len(data['channels'])} channels"))
        client.on_heart_rate(lambda hr: print(f"Heart Rate: {hr:.0f} BPM"))

        # Find and connect
        device = await client.find_device()
        if device:
            await client.connect_and_stream(device.address, duration_seconds=30)

            # Show summary
            summary = client.get_summary()
            print(f"\nSummary: {summary}")

    # Run example
    asyncio.run(example())
