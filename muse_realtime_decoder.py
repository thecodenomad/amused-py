"""
Muse Real-time Decoder
On-the-fly decoding of Muse S BLE packets with minimal latency

Provides instant access to sensor values without intermediate storage
"""

import struct
import numpy as np
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
import datetime
try:
    from scipy.signal import find_peaks
    from scipy.ndimage import uniform_filter1d
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    uniform_filter1d = None
    find_peaks = None

@dataclass
class DecodedData:
    """Container for decoded sensor data"""
    timestamp: datetime.datetime
    packet_type: str
    eeg: Optional[Dict[str, List[float]]] = None
    ppg: Optional[Dict[str, List[float]]] = None
    imu: Optional[Dict[str, List[float]]] = None
    heart_rate: Optional[float] = None
    battery: Optional[int] = None
    raw_bytes: bytes = b''

class MuseRealtimeDecoder:
    """
    Real-time packet decoder for Muse S data streams

    Features:
    - Zero-copy decoding where possible
    - Callback-based processing
    - Minimal memory footprint
    - Stream statistics
    - Adaptive Gen1/Gen3 support
    """

    def __init__(self, device_model: str = 'auto'):
        """
        Initialize decoder with device-specific settings

        Args:
            device_model: 'gen1', 'gen3', or 'auto' for adaptive detection
        """
        # Device configuration
        self.device_model = device_model
        self.detected_model = None

        # Channel configurations for different device types
        self.CHANNEL_CONFIGS = {
            'gen1': {
                'eeg_channels': ['TP9', 'AF7', 'AF8', 'TP10'],
                'max_channels': 4,
                'eeg_scale': 1000.0 / 2048.0,
                'imu_scale': 1.0 / 100.0
            },
            'gen3': {
                'eeg_channels': ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L'],
                'max_channels': 7,
                'eeg_scale': 488.28125 / 2048.0,  # Gen3 specific scaling
                'imu_scale': 2.0 / 32768.0       # Gen3 specific scaling
            }
        }

        # Calibration tables for different device types (all forehead-mounted)
        self.CALIBRATION_TABLES = {
            'gen1': {
                'ppg_scaling_factor': 1.0,        # Baseline scaling
                'ppg_baseline_offset': 0.0,       # Baseline adjustment
                'hr_scaling_factor': 1.0,         # Heart rate scaling (adjusted)
                'hr_baseline_offset': 0.0,        # Heart rate baseline adjustment (adjusted)
                'quality_threshold': 0.5,         # Signal quality threshold (lowered)
                'peak_prominence': 0.2,           # Peak detection prominence (adjusted)
                'ppg_range_min': 2000,            # Minimum valid PPG value
                'ppg_range_max': 45000            # Maximum valid PPG value
            },
            'gen3': {
                'ppg_scaling_factor': 1.0,        # Baseline scaling
                'ppg_baseline_offset': 0.0,       # Baseline adjustment
                'hr_scaling_factor': 1.0,         # Heart rate scaling (reference)
                'hr_baseline_offset': 0.0,        # Heart rate baseline adjustment
                'quality_threshold': 0.7,         # Signal quality threshold
                'peak_prominence': 0.3,           # Peak detection prominence
                'ppg_range_min': 5000,            # Minimum valid PPG value
                'ppg_range_max': 30000            # Maximum valid PPG value
            }
        }

        # Statistics (initialize before device configuration)
        self.stats = {
            'packets_decoded': 0,
            'eeg_samples': 0,
            'ppg_samples': 0,
            'imu_samples': 0,
            'decode_errors': 0,
            'last_packet_time': None,
            'device_model': self.device_model,
            'detected_model': None
        }

        # Start with Gen1 defaults, will adapt based on device_model
        self._configure_for_device('gen1')

        # Callbacks for different data types
        self.callbacks: Dict[str, List[Callable]] = {
            'eeg': [],
            'ppg': [],
            'imu': [],
            'heart_rate': [],
            'any': []  # Called for any packet
        }

        # Buffers for derived metrics
        self.ppg_buffer = []
        self.last_heart_rate = None

        # Adaptive detection state
        self.channel_count_history = []
        self.packets_analyzed = 0

    def _configure_for_device(self, model: str):
        """Configure decoder for specific device model"""
        if model in self.CHANNEL_CONFIGS:
            config = self.CHANNEL_CONFIGS[model]
            self.eeg_channels = config['eeg_channels']
            self.max_channels = config['max_channels']
            self.EEG_SCALE = config['eeg_scale']
            self.IMU_SCALE = config['imu_scale']
            self.detected_model = model
            self.stats['detected_model'] = model

    def _detect_device_model(self):
        """Detect device model (simplified - defaults to gen3)"""
        if self.device_model == 'auto':
            # Default to gen3 for now - could be enhanced with BLE characteristic detection
            self.device_model = 'gen3'
            self._configure_for_device('gen3')

    def _detect_device_and_site(self):
        """Detect device model (Muse headbands are always forehead-mounted)"""
        if self.device_model == 'auto':
            # Try to detect device model from BLE characteristics or packet patterns
            self.device_model = self._identify_device_model()

        # Muse headbands are designed for forehead placement only

    def _identify_device_model(self) -> str:
        """Identify Muse device model"""
        # Default to gen3 for now - could be enhanced with BLE characteristic detection
        return 'gen3'  # Muse S Gen3/Athena is the most common



    def _assess_signal_quality(self) -> float:
        """Assess PPG signal quality for heart rate calculation"""
        if len(self.ppg_buffer) < 50:  # Need minimum samples
            return 0.0

        try:
            # Calculate signal quality metrics
            signal_std = np.std(self.ppg_buffer[-200:] if len(self.ppg_buffer) > 200 else self.ppg_buffer)
            signal_mean = np.mean(self.ppg_buffer[-200:] if len(self.ppg_buffer) > 200 else self.ppg_buffer)

            if signal_mean == 0:
                return 0.0

            # Signal-to-noise ratio (simplified)
            snr = signal_std / (abs(signal_mean) + 1e-6)  # Avoid division by zero

            # Normalize quality score (0-1)
            # Good SNR threshold varies by device
            device_key = self.detected_model or 'gen3'
            calibration = self.CALIBRATION_TABLES.get(device_key, self.CALIBRATION_TABLES['gen3'])

            quality = min(float(snr) / 0.5, 1.0)  # 0.5 is good SNR threshold
            return quality

        except Exception:
            return 0.0

    def _adapt_device_model(self, packet_data: bytes):
        """Adapt device model based on packet analysis"""
        if self.device_model != 'auto':
            return  # Don't adapt if explicitly set

        self.packets_analyzed += 1

        # Analyze packet for device-specific patterns
        if len(packet_data) > 4:
            # Count potential EEG segments
            segment_count = 0
            offset = 4
            while offset + 18 <= len(packet_data):
                segment = packet_data[offset:offset+18]
                if self._looks_like_eeg(segment):
                    segment_count += 1
                offset += 18

            self.channel_count_history.append(segment_count)

            # Keep only recent history
            if len(self.channel_count_history) > 10:
                self.channel_count_history = self.channel_count_history[-10:]

            # Detect device based on typical channel counts
            if len(self.channel_count_history) >= 3:
                avg_channels = sum(self.channel_count_history) / len(self.channel_count_history)

                if avg_channels > 5 and self.detected_model != 'gen3':
                    self._configure_for_device('gen3')
                    print(f"[Decoder] Adapted to Gen3 (detected {avg_channels:.1f} avg channels)")
                elif avg_channels <= 4 and self.detected_model != 'gen1':
                    self._configure_for_device('gen1')
                    print(f"[Decoder] Adapted to Gen1 (detected {avg_channels:.1f} avg channels)")
    
    def register_callback(self, data_type: str, callback: Callable[[DecodedData], None]):
        """
        Register a callback for specific data type
        
        Args:
            data_type: 'eeg', 'ppg', 'imu', 'heart_rate', or 'any'
            callback: Function to call with decoded data
            
        Example:
            decoder.register_callback('eeg', lambda data: print(f"EEG: {data.eeg}"))
        """
        if data_type in self.callbacks:
            self.callbacks[data_type].append(callback)
    
    def decode(self, data: bytes, timestamp: Optional[datetime.datetime] = None) -> DecodedData:
        """
        Decode a raw BLE packet in real-time

        Args:
            data: Raw packet bytes
            timestamp: Packet timestamp

        Returns:
            DecodedData object with parsed values
        """
        if timestamp is None:
            timestamp = datetime.datetime.now()

        self.stats['packets_decoded'] += 1
        self.stats['last_packet_time'] = timestamp

        # Identify packet type
        if not data:
            return DecodedData(timestamp=timestamp, packet_type='EMPTY', raw_bytes=data)

        packet_type_byte = data[0]
        decoded = DecodedData(
            timestamp=timestamp,
            packet_type=self._get_packet_type(packet_type_byte),
            raw_bytes=data
        )

        # Adaptive device detection
        if self.device_model == 'auto':
            self._adapt_device_model(data)

        try:
            # Fast path decoding based on packet type
            if packet_type_byte == 0xDF:
                self._decode_type_df(data, decoded)
            elif packet_type_byte == 0xF4:
                self._decode_type_f4(data, decoded)
            elif packet_type_byte == 0xDB:
                self._decode_type_db(data, decoded)
            elif packet_type_byte == 0xD9:
                self._decode_type_d9(data, decoded)
            else:
                # Try generic decoding
                self._decode_generic(data, decoded)
        except Exception as e:
            self.stats['decode_errors'] += 1
            # Continue even if decoding fails

        # Trigger callbacks
        self._trigger_callbacks(decoded)

        return decoded
    
    def _get_packet_type(self, type_byte: int) -> str:
        """Get human-readable packet type"""
        types = {
            0xDF: 'EEG_PPG',
            0xF4: 'IMU',
            0xDB: 'MIXED_1',
            0xD9: 'MIXED_2'
        }
        return types.get(type_byte, f'UNKNOWN_{type_byte:02X}')
    
    def _decode_type_df(self, data: bytes, decoded: DecodedData):
        """Fast decode for 0xDF packets (EEG + PPG) - Adaptive Gen1/Gen3"""
        decoded.eeg = {}
        decoded.ppg = {}

        # Skip header (4 bytes)
        offset = 4
        channel_count = 0
        max_iterations = len(data)  # Prevent infinite loops
        iterations = 0

        # Use adaptive channel configuration based on detected device model
        channel_names = self.eeg_channels  # Use configured channels (Gen1 or Gen3)
        max_segments = self.max_channels   # Use configured max channels

        # Process up to the maximum number of channels for the detected device
        segment_count = 0
        while offset < len(data) and iterations < max_iterations and segment_count < max_segments:
            iterations += 1

            # Try EEG segment (18 bytes)
            if offset + 18 <= len(data):
                segment = data[offset:offset+18]

                # Check if this looks like EEG data
                if self._looks_like_eeg(segment):
                    samples = self._fast_unpack_eeg(segment)
                    if samples and len([s for s in samples if -500 < s < 500]) >= 4:  # At least 4 valid samples
                        channel_name = channel_names[channel_count] if channel_count < len(channel_names) else f'ch{channel_count}'
                        decoded.eeg[channel_name] = samples
                        self.stats['eeg_samples'] += len(samples)
                        channel_count += 1

                # Also try to extract PPG data from this segment
                ppg_samples = self._fast_unpack_ppg_from_eeg_segment(segment)
                if ppg_samples:
                    if 'samples' not in decoded.ppg:
                        decoded.ppg['samples'] = []
                    decoded.ppg['samples'].extend(ppg_samples)
                    self.stats['ppg_samples'] += len(ppg_samples)

                    # Update heart rate buffer
                    self.ppg_buffer.extend(ppg_samples)
                    if len(self.ppg_buffer) > 64:  # Reduced from 128 for faster initial HR
                        self._calculate_heart_rate(decoded)
                        if len(self.ppg_buffer) > 320:  # Keep max 5 seconds
                            self.ppg_buffer = self.ppg_buffer[-320:]

                offset += 18
                segment_count += 1
            else:
                break  # Not enough data left

        # If we found PPG data, log it
        if decoded.ppg and 'samples' in decoded.ppg:
            print(f"[Decoder] Found {len(decoded.ppg['samples'])} PPG samples from {self.detected_model} device")

    def decode_raw_packet(self, data: bytes, characteristic_uuid: str, timestamp=None) -> DecodedData:
        """
        Decode raw packet from specific characteristic UUID
        This handles the different packet types from different characteristics
        """
        if timestamp is None:
            timestamp = datetime.datetime.now()

        decoded = DecodedData(timestamp=timestamp, packet_type='RAW', raw_bytes=data)

        # Map characteristic UUIDs to data types based on raw capture analysis
        if characteristic_uuid == "273e0003-4c4d-454d-96be-f03bac821358":
            # TP9 EEG data
            decoded.eeg = {'TP9': self._fast_unpack_eeg(data)}
        elif characteristic_uuid == "273e0004-4c4d-454d-96be-f03bac821358":
            # AF7 EEG data
            decoded.eeg = {'AF7': self._fast_unpack_eeg(data)}
        elif characteristic_uuid == "273e0005-4c4d-454d-96be-f03bac821358":
            # AF8 EEG data
            decoded.eeg = {'AF8': self._fast_unpack_eeg(data)}
        elif characteristic_uuid == "273e0006-4c4d-454d-96be-f03bac821358":
            # TP10 EEG data
            decoded.eeg = {'TP10': self._fast_unpack_eeg(data)}
        elif characteristic_uuid in ["273e0009-4c4d-454d-96be-f03bac821358", "273e000a-4c4d-454d-96be-f03bac821358"]:
            # PPG data - use dedicated PPG unpacking for better accuracy
            ppg_samples = self._fast_unpack_ppg(data)
            if ppg_samples:
                decoded.ppg = {'samples': [float(s) for s in ppg_samples]}
                # Update PPG buffer for heart rate calculation
                self.ppg_buffer.extend(ppg_samples)
                if len(self.ppg_buffer) > 64:
                    self._calculate_heart_rate(decoded)
                    if len(self.ppg_buffer) > 320:
                        self.ppg_buffer = self.ppg_buffer[-320:]
        elif characteristic_uuid == "273e0008-4c4d-454d-96be-f03bac821358":
            # IMU data
            decoded.imu = self._decode_imu_data(data)

        return decoded

    def _decode_imu_data(self, data: bytes) -> Dict[str, List[float]]:
        """Decode IMU data from Gen1 characteristic"""
        if len(data) < 16:
            return {}

        try:
            # Extract accelerometer and gyroscope (16-bit signed values)
            ax = struct.unpack('>h', data[0:2])[0] / 100.0
            ay = struct.unpack('>h', data[2:4])[0] / 100.0
            az = struct.unpack('>h', data[4:6])[0] / 100.0
            gx = struct.unpack('>h', data[6:8])[0] / 100.0
            gy = struct.unpack('>h', data[8:10])[0] / 100.0
            gz = struct.unpack('>h', data[10:12])[0] / 100.0

            return {
                'accel': [ax, ay, az],
                'gyro': [gx, gy, gz]
            }
        except:
            return {}
    
    def _decode_type_f4(self, data: bytes, decoded: DecodedData):
        """Fast decode for 0xF4 packets (IMU)"""
        if len(data) < 16:
            return
        
        decoded.imu = {}
        offset = 4
        
        try:
            # Direct struct unpack for speed
            ax, ay, az, gx, gy, gz = struct.unpack_from('>hhhhhh', data, offset)
            
            decoded.imu['accel'] = [ax * self.IMU_SCALE, ay * self.IMU_SCALE, az * self.IMU_SCALE]
            decoded.imu['gyro'] = [gx * self.IMU_SCALE, gy * self.IMU_SCALE, gz * self.IMU_SCALE]
            self.stats['imu_samples'] += 2
        except:
            pass
    
    def _decode_type_db(self, data: bytes, decoded: DecodedData):
        """Fast decode for 0xDB packets (Mixed)"""
        # These often contain control data or mixed sensors
        self._decode_generic(data[4:], decoded)
    
    def _decode_type_d9(self, data: bytes, decoded: DecodedData):
        """Fast decode for 0xD9 packets (Mixed)"""
        # Similar to 0xDB
        self._decode_generic(data[4:], decoded)
    
    def _decode_generic(self, data: bytes, decoded: DecodedData):
        """Generic decoder for unknown packet types"""
        # Look for known patterns
        offset = 0
        
        while offset < len(data) - 10:
            # Check for EEG pattern
            if offset + 18 <= len(data) and self._looks_like_eeg(data[offset:offset+18]):
                if decoded.eeg is None:
                    decoded.eeg = {}
                samples = self._fast_unpack_eeg(data[offset:offset+18])
                # Use proper channel names for Muse S
                channel_names = ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']
                ch_idx = len(decoded.eeg)
                channel_name = channel_names[ch_idx] if ch_idx < len(channel_names) else f'ch{ch_idx}'
                decoded.eeg[channel_name] = samples
                self.stats['eeg_samples'] += len(samples)
                offset += 18
            else:
                offset += 1
    
    def _looks_like_eeg(self, segment: bytes) -> bool:
        """Quick check if segment contains EEG data"""
        if len(segment) != 18:
            return False
        
        # Check first sample range
        sample = (segment[0] << 4) | (segment[1] >> 4)
        return 1000 < sample < 3000
    
    def _fast_unpack_eeg(self, data: bytes) -> List[float]:
        """Fast EEG unpacking using numpy if available"""
        samples = []
        
        # Unpack 12 samples from 18 bytes
        for i in range(6):
            offset = i * 3
            # Two 12-bit samples in 3 bytes
            b0, b1, b2 = data[offset:offset+3]
            
            sample1 = (b0 << 4) | (b1 >> 4)
            sample2 = ((b1 & 0x0F) << 8) | b2
            
            # Convert to microvolts
            samples.append((sample1 - 2048) * self.EEG_SCALE)
            samples.append((sample2 - 2048) * self.EEG_SCALE)
        
        return samples
    
    def _fast_unpack_ppg(self, data: bytes) -> List[int]:
        """Fast PPG unpacking - Device-specific extraction with calibration"""
        if len(data) < 6:
            return []

        samples = []

        # Get device-specific calibration for range validation
        device_key = self.detected_model or 'gen3'
        calibration = self.CALIBRATION_TABLES.get(device_key, self.CALIBRATION_TABLES['gen3'])

        # Apply device-specific PPG extraction based on detected model
        if self.detected_model == 'gen1':
            # Gen1 PPG data extraction - optimized for Gen1 characteristics
            # Gen1 uses different PPG encoding than Gen3

            # For Gen1: Look for PPG data in 16-bit chunks
            for i in range(0, len(data) - 1, 2):
                if i + 1 < len(data):
                    val = (data[i] << 8) | data[i+1]

                    # Use calibration-based range validation
                    if calibration['ppg_range_min'] <= val <= calibration['ppg_range_max']:
                        # Apply device-specific scaling and baseline adjustment
                        calibrated_val = int(val * calibration['ppg_scaling_factor'] + calibration['ppg_baseline_offset'])
                        samples.append(calibrated_val)

            # If we didn't get enough samples, try Gen1-specific 20-bit extraction
            if len(samples) < 3:
                samples = []
                for i in range(0, len(data) - 2, 3):
                    if i + 2 < len(data):
                        # Gen1 20-bit sample extraction
                        val = ((data[i] & 0x0F) << 16) | (data[i+1] << 8) | data[i+2]
                        if calibration['ppg_range_min'] <= val <= calibration['ppg_range_max']:
                            calibrated_val = int(val * calibration['ppg_scaling_factor'] + calibration['ppg_baseline_offset'])
                            samples.append(calibrated_val)
        else:
            # Gen3 (default) PPG extraction - use calibration for validation
            for i in range(0, 18, 3):
                if i + 2 < len(data):
                    # 20-bit samples, simplified to 16-bit for speed
                    val = (data[i] << 8) | data[i+1]
                    if calibration['ppg_range_min'] <= val <= calibration['ppg_range_max']:
                        calibrated_val = int(val * calibration['ppg_scaling_factor'] + calibration['ppg_baseline_offset'])
                        samples.append(calibrated_val)

        return samples if len(samples) > 2 else []

    def _fast_unpack_ppg_from_eeg_segment(self, data: bytes) -> List[int]:
        """Extract PPG data from EEG segment - Device-specific extraction"""
        if len(data) < 18:
            return []

        samples = []

        # Apply device-specific PPG extraction from EEG segments
        if self.detected_model == 'gen1':
            # Gen1 PPG data embedded in EEG segments has specific characteristics
            for i in range(0, len(data) - 1, 2):
                if i + 1 < len(data):
                    val = (data[i] << 8) | data[i+1]

                    # Gen1 PPG values in EEG segments are typically:
                    # - Higher than EEG values (EEG usually < 4096)
                    # - In a specific range for Gen1 PPG sensors
                    if 4096 < val < 55000:  # Gen1 PPG range in EEG segments
                        samples.append(val)
        else:
            # Gen3 (default) - original logic preserved
            # Look for PPG-like values in the EEG segment
            for i in range(0, 16, 2):  # Check pairs of bytes
                if i + 2 <= len(data):
                    val = (data[i] << 8) | data[i+1]
                    if val > 10000:  # PPG range check
                        samples.append(val)

        return samples if len(samples) > 0 else []
    
    def _calculate_heart_rate(self, decoded: DecodedData):
        """Calculate heart rate from PPG buffer with device-specific calibration"""
        if len(self.ppg_buffer) < 32:  # Basic threshold
            return

        # Get device-specific calibration
        device_model = self.detected_model or 'gen3'
        calibration = self.CALIBRATION_TABLES.get(device_model, self.CALIBRATION_TABLES['gen3'])

        # Assess signal quality first
        quality_score = self._assess_signal_quality()

        # Only proceed if signal quality meets threshold
        if quality_score < calibration['quality_threshold']:
            print(f"[Decoder] Signal quality too low ({quality_score:.2f} < {calibration['quality_threshold']})")
            return

        try:
            signal = np.array(self.ppg_buffer[-640:] if len(self.ppg_buffer) > 640 else self.ppg_buffer)

            # Apply device-specific signal preprocessing
            signal = signal - np.mean(signal)

            if not SCIPY_AVAILABLE:
                return

            # Apply device-specific PPG scaling and baseline adjustment
            signal = signal * calibration['ppg_scaling_factor'] + calibration['ppg_baseline_offset']

            # Apply device-specific heart rate calculation
            if self.detected_model == 'gen1':
                # Gen1-optimized heart rate calculation
                if len(self.ppg_buffer) < 64:  # Need more data for reliable Gen1 detection
                    return

                # Apply light smoothing to reduce noise (Gen1 optimization)
                if len(signal) > 10 and uniform_filter1d is not None:
                    signal = uniform_filter1d(signal, size=5)  # More smoothing for Gen1

                # First, try to detect the actual sampling rate from the PPG data
                detected_rate = self._detect_ppg_sampling_rate(self.ppg_buffer)
                print(f"[Decoder] Detected PPG sampling rate: {detected_rate}Hz")

                # Gen1-optimized: Prioritize lower sampling rates typical of Gen1
                rates_to_try = [detected_rate]
                if detected_rate == 16.0:
                    rates_to_try.extend([21.33])  # Only add one alternative
                elif detected_rate == 21.33:
                    rates_to_try.extend([16.0, 32.0])  # Gen1 most common
                elif detected_rate == 32.0:
                    rates_to_try.extend([21.33])  # Conservative approach
            else:
                # Gen3 (default) heart rate calculation - original logic preserved
                if len(self.ppg_buffer) < 64:  # Reduced from 128 for faster initial HR
                    return

                # Original Gen3 logic
                detected_rate = self._detect_ppg_sampling_rate(self.ppg_buffer)
                print(f"[Decoder] Detected PPG sampling rate: {detected_rate}Hz")

                # Original Gen3 sampling rate selection
                rates_to_try = [detected_rate]
                if detected_rate == 32.0:
                    rates_to_try.extend([16.0, 21.33, 24.0])
                elif detected_rate == 64.0:
                    rates_to_try.extend([32.0, 42.67, 48.0])

            for sample_rate in rates_to_try:
                # Apply device-specific peak detection parameters
                if self.detected_model == 'gen1':
                    # Gen1-optimized peak detection parameters - use calibration values
                    min_distance = sample_rate / 2.5  # Max HR ~150 BPM (more conservative)
                    max_distance = sample_rate / 0.8  # Min HR ~48 BPM (higher minimum)

                    # Use calibration-based prominence threshold
                    prominence_threshold = np.std(signal) * calibration['peak_prominence']
                    height_threshold = np.mean(signal) + np.std(signal) * 0.05  # Lower height

                    if not SCIPY_AVAILABLE:
                        return
                    peaks, _ = find_peaks(signal,  # type: ignore
                                        distance=min_distance,
                                        prominence=prominence_threshold,
                                        height=height_threshold,
                                        width=2)  # Minimum peak width

                    if len(peaks) >= 3:  # Require more peaks for stability
                        peak_intervals = np.diff(peaks) / sample_rate

                        # Filter out outliers (peaks that are too close or too far)
                        valid_intervals = [interval for interval in peak_intervals
                                          if 0.4 <= interval <= 1.25]  # 48-150 BPM range

                        if len(valid_intervals) >= 2:
                            raw_hr = 60.0 / np.mean(valid_intervals)

                            # Apply device-specific calibration
                            calibrated_hr = raw_hr * calibration['hr_scaling_factor'] + calibration['hr_baseline_offset']

                            # Gen1-optimized valid range - more conservative
                            if 45 <= calibrated_hr <= 130:  # Conservative range for Gen1
                                decoded.heart_rate = float(calibrated_hr)
                                self.last_heart_rate = float(calibrated_hr)
                                print(f"[Decoder] Calibrated HR: {calibrated_hr:.1f} BPM ({self.detected_model}) at {sample_rate}Hz")
                                break
                else:
                    # Gen3 (default) peak detection - use calibration values
                    if not SCIPY_AVAILABLE:
                        return
                    peaks, _ = find_peaks(signal, distance=40, prominence=np.std(signal)*calibration['peak_prominence'])  # type: ignore

                    if len(peaks) > 1:
                        # Calculate heart rate
                        peak_intervals = np.diff(peaks) / sample_rate  # Use detected rate
                        raw_hr = 60.0 / np.mean(peak_intervals)

                        # Apply device-specific calibration
                        calibrated_hr = raw_hr * calibration['hr_scaling_factor'] + calibration['hr_baseline_offset']

                        if 40 < calibrated_hr < 200:  # Physiological range
                            decoded.heart_rate = float(calibrated_hr)
                            self.last_heart_rate = float(calibrated_hr)
                            print(f"[Decoder] Calibrated HR: {calibrated_hr:.1f} BPM ({self.detected_model}) at {sample_rate}Hz")
                            break
        except Exception as e:
            print(f"[Decoder] Heart rate calculation error: {e}")
            pass

    def _detect_ppg_sampling_rate(self, ppg_data: List[int]) -> float:
        """Detect actual PPG sampling rate - Device-specific detection"""
        if len(ppg_data) < 20:
            return 21.33 if self.detected_model == 'gen1' else 64.0  # Device-specific default

        signal = np.array(ppg_data, dtype=float)
        signal = signal - np.mean(signal)

        if len(signal) < 50:
            return 21.33 if self.detected_model == 'gen1' else 64.0  # Device-specific default

        # Apply device-specific sampling rate detection
        if self.detected_model == 'gen1':
            # Gen1-specific sampling rate detection - prioritize lower rates
            # Gen1 devices typically use lower sampling rates than Gen3

            # Method 1: Gen1-specific signal characteristics - focus on resting HR range
            if len(signal) >= 64:
                try:
                    # Gen1 PPG signals often have more consistent periodicity
                    # Look for heart rate frequencies typical of Gen1 (slower sampling)
                    window_size = min(64, len(signal))
                    spectrum = []

                    # Gen1 typical frequencies (lower than Gen3) - focus on resting HR range
                    for freq in [6, 8, 10, 12, 15]:  # Gen1 PPG frequencies for 60-100 BPM
                        period_samples = len(signal) // (freq * (len(signal) / 256.0))
                        if period_samples > 1:
                            sine_wave = np.sin(2 * np.pi * np.arange(len(signal)) / period_samples)
                            correlation = np.abs(np.correlate(signal, sine_wave, mode='valid'))
                            spectrum.append((freq, np.mean(correlation)))

                    if spectrum:
                        best_freq = max(spectrum, key=lambda x: x[1])[0]

                        # Gen1 sampling rate mapping - MORE conservative approach
                        if 5 <= best_freq <= 10:    # Low frequency PPG (resting HR) - expanded range
                            return 16.0
                        elif 10 <= best_freq <= 15: # Medium frequency PPG
                            return 21.33
                        else:                       # Higher frequency PPG
                            return 16.0  # Default to 16.0 Hz for Gen1 (more conservative)
                except:
                    pass

            # Method 2: Gen1 statistical approach - more conservative
            std_dev = np.std(signal)
            mean_val = np.mean(np.abs(signal))

            # Gen1 PPG data typically has different variability patterns
            # Be more conservative with rate selection - bias toward lower rates
            if std_dev < 500:      # Gen1 low variability (likely resting) - lower threshold
                return 16.0
            elif std_dev < 1500:   # Gen1 medium variability - lower threshold
                return 16.0        # Changed from 21.33 to 16.0
            elif std_dev < 2500:   # Gen1 high variability - lower threshold
                return 21.33
            else:                  # Gen1 very high variability
                return 16.0        # Changed from 21.33 to 16.0

            return 16.0  # Gen1 safe default - changed from 21.33 to 16.0
        else:
            # Gen3 (default) sampling rate detection - original logic preserved
            # Check for common sampling rates by looking at signal variance patterns
            if len(signal) > 50:
                # Calculate autocorrelation to find periodicity
                corr = np.correlate(signal - np.mean(signal), signal - np.mean(signal), mode='full')
                corr = corr[len(corr)//2:]

                # Find peaks in autocorrelation
                if not SCIPY_AVAILABLE:
                    return 64.0  # Gen3 default
                peaks, _ = find_peaks(corr[:len(corr)//4], distance=10, prominence=np.std(corr)*0.1)  # type: ignore

                if len(peaks) > 0:
                    # Estimate period from first peak
                    period = peaks[0]
                    estimated_rate = len(ppg_data) / (period * 0.1)  # Rough estimate

                    # Snap to common rates
                    if 25 <= estimated_rate <= 40:
                        return 32.0
                    elif 50 <= estimated_rate <= 75:
                        return 64.0
                    elif 100 <= estimated_rate <= 140:
                        return 128.0

            return 64.0  # Gen3 default

    def _trigger_callbacks(self, decoded: DecodedData):
        """Trigger registered callbacks"""
        # Type-specific callbacks
        if decoded.eeg and self.callbacks['eeg']:
            for callback in self.callbacks['eeg']:
                callback(decoded)
        
        if decoded.ppg and self.callbacks['ppg']:
            for callback in self.callbacks['ppg']:
                callback(decoded)
        
        if decoded.imu and self.callbacks['imu']:
            for callback in self.callbacks['imu']:
                callback(decoded)
        
        if decoded.heart_rate and self.callbacks['heart_rate']:
            for callback in self.callbacks['heart_rate']:
                callback(decoded)
        
        # General callbacks
        for callback in self.callbacks['any']:
            callback(decoded)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get decoder statistics"""
        return {
            'packets_decoded': self.stats['packets_decoded'],
            'eeg_samples': self.stats['eeg_samples'],
            'ppg_samples': self.stats['ppg_samples'],
            'imu_samples': self.stats['imu_samples'],
            'decode_errors': self.stats['decode_errors'],
            'error_rate': self.stats['decode_errors'] / max(1, self.stats['packets_decoded']),
            'last_heart_rate': self.last_heart_rate,
            'last_packet': self.stats['last_packet_time']
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            'packets_decoded': 0,
            'eeg_samples': 0,
            'ppg_samples': 0,
            'imu_samples': 0,
            'decode_errors': 0,
            'last_packet_time': None
        }

# Example real-time processing
def example_realtime_processing():
    """Example of real-time packet processing"""
    
    print("Real-time Decoder Example")
    print("=" * 60)
    
    # Create decoder
    decoder = MuseRealtimeDecoder()
    
    # Register callbacks for different data types
    def on_eeg(data: DecodedData):
        if data.eeg:
            # Get first available channel
            first_channel = next(iter(data.eeg.keys()))
            print(f"EEG: {len(data.eeg)} channels, {first_channel}: {data.eeg[first_channel][0]:.1f} μV")
    
    def on_heart_rate(data: DecodedData):
        print(f"Heart Rate: {data.heart_rate:.0f} BPM")
    
    def on_imu(data: DecodedData):
        if data.imu:
            print(f"IMU: Accel={data.imu['accel']}, Gyro={data.imu['gyro']}")
    
    decoder.register_callback('eeg', on_eeg)
    decoder.register_callback('heart_rate', on_heart_rate)
    decoder.register_callback('imu', on_imu)
    
    # Simulate incoming packets
    test_packets = [
        bytes.fromhex("df0000" + "80088008" * 10),  # EEG packet
        bytes.fromhex("f40200" + "0100020003000400050006" * 2),  # IMU packet
    ]
    
    for packet in test_packets:
        decoded = decoder.decode(packet)
        print(f"Decoded: {decoded.packet_type}")
    
    # Show statistics
    stats = decoder.get_stats()
    print(f"\nStatistics:")
    print(f"  Packets: {stats['packets_decoded']}")
    print(f"  EEG samples: {stats['eeg_samples']}")
    print(f"  Error rate: {stats['error_rate']:.1%}")

if __name__ == "__main__":
    example_realtime_processing()