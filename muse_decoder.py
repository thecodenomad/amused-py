"""
Muse Real-time Decoder
Clean, modular decoder for Muse S BLE packets
"""

import struct
import numpy as np
from typing import Dict, List, Optional, Callable, Any, Union
from dataclasses import dataclass
import datetime
import logging

# Device configurations (fallback if config module not available)
DEVICE_CONFIGS = {
    'gen1': {
        'name': 'Muse S Gen 1',
        'eeg_scale': 1000.0 / 2048.0,
        'imu_scale': 1.0 / 100.0,
        'ppg_scale': 1.0,
        'ppg_offset': 0.0,
        'hr_scale': 1.0,
        'hr_offset': 0.0,
        'quality_threshold': 0.05,
        'peak_prominence': 0.2,
        'ppg_range_min': 800,
        'ppg_range_max': 65000,
            'sampling_rate': 16.0,  # Reverted to 16.0 Hz as found more accurate
        'stabilization_time': 5.0,
        'eeg_channels': ['TP9', 'AF7', 'AF8', 'TP10'],
        'max_channels': 4,
    },
    'gen3': {
        'name': 'Muse S Gen 3',
        'eeg_scale': 488.28125 / 2048.0,
        'imu_scale': 2.0 / 32768.0,
        'ppg_scale': 1.0,
        'ppg_offset': 0.0,
        'hr_scale': 1.0,
        'hr_offset': 0.0,
        'quality_threshold': 0.7,
        'peak_prominence': 0.3,
        'ppg_range_min': 5000,
        'ppg_range_max': 30000,
        'sampling_rate': 64.0,
        'stabilization_time': 2.0,
        'eeg_channels': ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L'],
        'max_channels': 7,
    }
}

def get_device_config(model: str) -> Dict[str, Any]:
    """Get device configuration"""
    return DEVICE_CONFIGS.get(model, DEVICE_CONFIGS['gen3'])

try:
    from scipy.signal import find_peaks
    from scipy.ndimage import uniform_filter1d
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    uniform_filter1d = None
    find_peaks = None

logger = logging.getLogger(__name__)


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


class SignalQualityAssessor:
    """Assess signal quality for PPG data"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.quality_threshold = config['quality_threshold']

    def assess_quality(self, signal: np.ndarray) -> float:
        """Assess PPG signal quality using multiple metrics - improved for real physiological data"""
        if len(signal) < 20:  # Reduced minimum for real-time processing
            return 0.0

        try:
            # Remove DC component
            signal = signal - np.mean(signal)

            if len(signal) < 5:
                return 0.0

            # Calculate quality metrics
            signal_std = np.std(signal)
            signal_range = np.ptp(signal)
            signal_mean = abs(np.mean(signal))

            if signal_std == 0 or signal_range == 0:
                return 0.0

            # Improved SNR estimation for PPG signals
            rms_signal = np.sqrt(np.mean(signal**2))

            # Use different noise estimation for PPG
            if len(signal) > 15:
                # For PPG, use a simpler noise estimate
                noise_estimate = np.std(np.diff(signal))  # First derivative noise
                snr = rms_signal / (noise_estimate + 1e-6)
            else:
                snr = signal_range / (signal_std + 1e-6)

            # Amplitude stability (coefficient of variation)
            cv_amplitude = signal_std / (signal_mean + 1e-6)

            # Dynamic range quality
            dynamic_range_ratio = signal_range / (signal_std + 1e-6)

            # PPG-specific quality metrics
            # For PPG, we want good amplitude variation but not too much noise
            amplitude_score = min(signal_range / 100.0, 1.0)  # Scale amplitude to 0-1

            # Combine metrics with PPG-optimized weights
            snr_score = min(float(snr) / 3.0, 1.0)  # More permissive SNR scaling
            stability_score = max(0.0, 1.0 - float(cv_amplitude) * 2.0)  # Adjusted stability
            dynamic_score = min(float(dynamic_range_ratio) / 8.0, 1.0)  # More permissive dynamic range
            amplitude_score = min(amplitude_score, 1.0)

            quality_score = (
                0.4 * snr_score +
                0.2 * stability_score +
                0.2 * dynamic_score +
                0.2 * amplitude_score
            )

            # More permissive threshold for Gen1 devices with real PPG data
            min_threshold = self.quality_threshold if self.config.get('name', '').startswith('Muse S Gen 3') else max(0.01, self.quality_threshold * 0.3)

            return min(quality_score, 1.0) if quality_score >= min_threshold else 0.0

        except Exception:
            return 0.0


class HeartRateProcessor:
    """Process PPG data to extract heart rate"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ppg_buffer = []
        self.quality_assessor = SignalQualityAssessor(config)

        # Heart rate filtering
        self.heart_rate_history = []
        self.filtered_hr = None

        # Calibration
        self.adaptive_offset = 0.0
        self.adaptive_scale = 1.0

    def add_ppg_samples(self, samples):
        """Add PPG samples to buffer"""
        # Convert to integers for storage (PPG values are typically integers)
        int_samples = [int(s) for s in samples]
        self.ppg_buffer.extend(int_samples)
        self._manage_buffer_size()

    def calculate_heart_rate(self) -> Optional[float]:
        """Calculate heart rate from PPG buffer with improved real-time processing"""
        print(f"[HR CALC] Called with {len(self.ppg_buffer)} samples")

        # Reduced minimum for real-time processing
        min_samples = 20 if self.config.get('sampling_rate', 64) == 16 else 32

        if len(self.ppg_buffer) < min_samples:
            print(f"[HR CALC] Not enough samples: {len(self.ppg_buffer)} < {min_samples}")
            return None

        # Assess signal quality with more recent data
        signal = np.array(self.ppg_buffer[-320:] if len(self.ppg_buffer) > 320 else self.ppg_buffer)
        quality = self.quality_assessor.assess_quality(signal)

        # More permissive quality check for real physiological data
        min_quality = self.config['quality_threshold'] * 0.5 if self.config.get('name', '').startswith('Muse S Gen 1') else self.config['quality_threshold']

        # Debug output
        print(f"[HR Debug] Buffer size: {len(self.ppg_buffer)}, Quality: {quality:.3f}, Min quality: {min_quality:.3f}")

        if quality < min_quality and len(self.ppg_buffer) < 100:  # Allow lower quality for initial readings
            print(f"[HR Debug] Quality too low: {quality:.3f} < {min_quality:.3f}")
            return None

        try:
            # Preprocessing
            signal = signal - np.mean(signal)
            signal = signal * self.config['ppg_scale'] + self.config['ppg_offset']

            # Light smoothing for noise reduction
            if len(signal) > 10 and uniform_filter1d is not None:
                smoothing_size = 3 if self.config.get('sampling_rate', 64) == 16 else 5
                signal = uniform_filter1d(signal, size=smoothing_size)

            # Peak detection
            peaks = self._detect_peaks(signal)
            print(f"[HR Debug] Found {len(peaks)} peaks")
            if len(peaks) < 2:
                print(f"[HR Debug] Not enough peaks: {len(peaks)}")
                return None

            # Calculate intervals and filter
            intervals = np.diff(peaks) / self.config['sampling_rate']
            valid_intervals = [i for i in intervals if 0.4 <= i <= 2.0]  # Slightly wider range

            if len(valid_intervals) < 1:
                return None

            # Use median for robustness, but also try mean if median seems outlier
            median_interval = np.median(valid_intervals)

            # Check if median is reasonable, otherwise use mean of valid intervals
            if len(valid_intervals) >= 3:
                mean_interval = np.mean(valid_intervals)
                # If median differs significantly from mean, use mean (handles outliers better)
                if abs(median_interval - mean_interval) / mean_interval > 0.3:
                    median_interval = mean_interval

            # Calculate heart rate
            raw_hr = 60.0 / median_interval
            calibrated_hr = raw_hr * self.config['hr_scale'] + self.config['hr_offset']
            final_hr = calibrated_hr * self.adaptive_scale + self.adaptive_offset

            # Filter and validate
            filtered_hr = self._filter_heart_rate(final_hr)

            # More inclusive range for real physiological data
            if 45 <= filtered_hr <= 160:  # Wider range for real data
                return float(filtered_hr)

        except Exception as e:
            logger.warning(f"Heart rate calculation failed: {e}")
            return None

    def _detect_peaks(self, signal: np.ndarray) -> np.ndarray:
        """Detect peaks in PPG signal with improved parameters for physiological data"""
        if not SCIPY_AVAILABLE or len(signal) < 20:  # Reduced minimum for real-time
            return np.array([])

        try:
            sampling_rate = self.config['sampling_rate']

            # Physiological heart rate range: 50-150 BPM
            min_hr_period = 60.0 / 150.0  # Fastest expected period (0.4 sec)
            max_hr_period = 60.0 / 50.0   # Slowest expected period (1.2 sec)

            min_distance = max(5, int(sampling_rate * min_hr_period))  # Min samples between peaks
            max_distance = int(sampling_rate * max_hr_period)  # Max samples between peaks

            # Adaptive prominence based on signal characteristics
            signal_std = np.std(signal)
            signal_range = np.ptp(signal)

            # For PPG signals, prominence should be based on signal amplitude
            base_prominence = max(signal_std * 0.1, signal_range * 0.05)  # More permissive
            prominence = base_prominence * self.config['peak_prominence']

            # Height threshold - should be above mean but not too restrictive
            signal_mean = np.mean(signal)
            height = signal_mean + signal_std * 0.1  # Less restrictive than before

            if find_peaks is not None:
                peaks, _ = find_peaks(
                    signal,
                    distance=min_distance,
                    prominence=prominence,
                    height=height,
                    width=1  # Allow narrow peaks
                )
            else:
                peaks = np.array([])

            # If traditional peak detection fails, try moving average method
            if len(peaks) < 2:
                peaks = self._detect_peaks_moving_average(signal, sampling_rate, quality_score=0.5)

            return peaks

        except Exception:
            return np.array([])

    def _detect_peaks_moving_average(self, signal: np.ndarray, sample_rate: float, quality_score: float) -> np.ndarray:
        """Advanced peak detection using moving average threshold - from muse_realtime_decoder.py"""
        if len(signal) < int(sample_rate * 2):  # Need at least 2 seconds of data
            return np.array([])

        try:
            # Calculate moving average with adaptive window size
            window_size = int(sample_rate * 0.75)  # 0.75s window
            if window_size < 3:
                window_size = 3

            # Create moving average filter
            ma_filter = np.ones(window_size * 2 + 1) / (window_size * 2 + 1)
            moving_avg = np.convolve(signal, ma_filter, mode='same')

            # Handle edges
            edge_size = window_size
            signal_mean = np.mean(signal)
            moving_avg[:edge_size] = signal_mean
            moving_avg[-edge_size:] = signal_mean

            # Find intersections where signal crosses moving average
            intersections = []
            for i in range(1, len(signal)):
                if signal[i-1] <= moving_avg[i-1] and signal[i] > moving_avg[i]:
                    intersections.append(i)

            # Find peaks between intersections
            peaks = []
            for i in range(len(intersections) - 1):
                start_idx = intersections[i]
                end_idx = intersections[i + 1]

                # Find maximum in this region
                if end_idx - start_idx > 3:  # Minimum width requirement
                    region_max_idx = start_idx + np.argmax(signal[start_idx:end_idx])
                    peaks.append(region_max_idx)

            peaks_array = np.array(peaks)

            # Apply quality-based filtering
            if len(peaks_array) >= 2 and quality_score > 0.3:
                # Calculate RR intervals
                rr_intervals = np.diff(peaks_array) / sample_rate

                # Filter based on physiological ranges and quality
                valid_peaks = [peaks_array[0]]  # Always include first peak

                for i in range(1, len(peaks_array)):
                    interval = rr_intervals[i-1]
                    # More permissive filtering for lower quality signals
                    min_interval = 0.4 if quality_score < 0.6 else 0.3
                    max_interval = 2.0 if quality_score < 0.6 else 1.8

                    if min_interval <= interval <= max_interval:
                        valid_peaks.append(peaks_array[i])

                peaks_array = np.array(valid_peaks)

            return peaks_array

        except Exception:
            return np.array([])

    def _filter_heart_rate(self, new_hr: float) -> float:
        """Apply filtering to stabilize heart rate readings"""
        self.heart_rate_history.append(new_hr)

        if len(self.heart_rate_history) > 15:
            self.heart_rate_history = self.heart_rate_history[-15:]

        if len(self.heart_rate_history) >= 5:
            median_hr = float(np.median(self.heart_rate_history))
            filtered_readings = [hr for hr in self.heart_rate_history
                               if abs(hr - median_hr) <= 8]

            if len(filtered_readings) >= 5:
                if self.filtered_hr is None:
                    self.filtered_hr = float(np.mean(filtered_readings))
                else:
                    alpha = 0.15
                    current_mean = float(np.mean(filtered_readings))
                    self.filtered_hr = alpha * current_mean + (1 - alpha) * self.filtered_hr

                return self.filtered_hr

        return new_hr

    def _manage_buffer_size(self):
        """Manage PPG buffer size"""
        max_size = 640  # 10 seconds at 64Hz
        if len(self.ppg_buffer) > max_size:
            self.ppg_buffer[:] = self.ppg_buffer[-max_size:]


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
        Initialize decoder

        Args:
            device_model: 'gen1', 'gen3', or 'auto' for adaptive detection
        """
        self.device_model = device_model
        self.config = get_device_config('gen1')  # Default, will be updated
        self.detected_model = None

        # Initialize components
        self.quality_assessor = SignalQualityAssessor(self.config)
        self.heart_rate_processor = HeartRateProcessor(self.config)

        # Statistics
        self.stats = {
            'packets_decoded': 0,
            'eeg_samples': 0,
            'ppg_samples': 0,
            'imu_samples': 0,
            'decode_errors': 0,
            'last_packet_time': None,
        }

        # Callbacks
        self.callbacks: Dict[str, List[Callable]] = {
            'eeg': [],
            'ppg': [],
            'imu': [],
            'heart_rate': [],
            'any': []
        }

        # Configure for initial device model
        self._configure_for_device('gen1')

    def _configure_for_device(self, model: str):
        """Configure decoder for specific device model"""
        self.config = get_device_config(model)
        self.detected_model = model
        self.stats['detected_model'] = model

        # Update components with new config
        self.quality_assessor = SignalQualityAssessor(self.config)
        self.heart_rate_processor = HeartRateProcessor(self.config)

    def register_callback(self, data_type: str, callback: Callable[[DecodedData], None]):
        """
        Register a callback for specific data type

        Args:
            data_type: 'eeg', 'ppg', 'imu', 'heart_rate', or 'any'
            callback: Function to call with decoded data
        """
        if data_type in self.callbacks:
            self.callbacks[data_type].append(callback)

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
            decoded.eeg = {'TP9': self._unpack_eeg(data)}
            self.stats['eeg_samples'] += len(decoded.eeg['TP9'])
        elif characteristic_uuid == "273e0004-4c4d-454d-96be-f03bac821358":
            # AF7 EEG data
            decoded.eeg = {'AF7': self._unpack_eeg(data)}
            self.stats['eeg_samples'] += len(decoded.eeg['AF7'])
        elif characteristic_uuid == "273e0005-4c4d-454d-96be-f03bac821358":
            # AF8 EEG data
            decoded.eeg = {'AF8': self._unpack_eeg(data)}
            self.stats['eeg_samples'] += len(decoded.eeg['AF8'])
        elif characteristic_uuid == "273e0006-4c4d-454d-96be-f03bac821358":
            # TP10 EEG data
            decoded.eeg = {'TP10': self._unpack_eeg(data)}
            self.stats['eeg_samples'] += len(decoded.eeg['TP10'])
        elif characteristic_uuid in ["273e0009-4c4d-454d-96be-f03bac821358", "273e000a-4c4d-454d-96be-f03bac821358"]:
            # PPG data - use dedicated PPG unpacking for better accuracy
            ppg_samples = self._unpack_ppg(data)
            if ppg_samples:
                decoded.ppg = {'samples': [float(s) for s in ppg_samples]}
                self.stats['ppg_samples'] += len(ppg_samples)
                self.heart_rate_processor.add_ppg_samples(ppg_samples)

                # Try to calculate heart rate from accumulated PPG data
                hr = self.heart_rate_processor.calculate_heart_rate()
                if hr is not None:
                    decoded.heart_rate = hr
                    print(f"[RAW PACKET] Heart rate calculated: {hr:.1f} BPM")
        elif characteristic_uuid == "273e0008-4c4d-454d-96be-f03bac821358":
            # IMU data
            decoded.imu = self._decode_imu_data(data)
            if decoded.imu:
                self.stats['imu_samples'] += 2

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

    def _unpack_ppg(self, data: bytes) -> List[int]:
        """Fast PPG unpacking - Optimized device-specific extraction"""
        if len(data) < 6:
            return []

        # Get device configuration for efficient access
        min_val, max_val = self.config['ppg_range_min'], self.config['ppg_range_max']

        samples = []

        if self.detected_model == 'gen1':
            # Gen1: Optimized 16-bit extraction with range validation
            for i in range(0, len(data) - 1, 2):
                val = (data[i] << 8) | data[i+1]
                if min_val <= val <= max_val:
                    samples.append(val)

            # Fallback to 20-bit if insufficient samples
            if len(samples) < 3:
                samples = []
                for i in range(0, len(data) - 2, 3):
                    val = ((data[i] & 0x0F) << 16) | (data[i+1] << 8) | data[i+2]
                    if min_val <= val <= max_val:
                        samples.append(val)
        else:
            # Gen3: Streamlined 16-bit extraction
            for i in range(0, min(18, len(data) - 1), 3):
                val = (data[i] << 8) | data[i+1]
                if val > 10000:  # PPG threshold
                    samples.append(val)

        return samples if len(samples) > 2 else []

    def decode(self, data: bytes, timestamp: Optional[datetime.datetime] = None) -> DecodedData:
        """
        Decode a raw BLE packet

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
        packet_type_str = self._get_packet_type(packet_type_byte)
        print(f"[PACKET] Type: 0x{packet_type_byte:02X} ({packet_type_str}), Length: {len(data)}")
        decoded = DecodedData(
            timestamp=timestamp,
            packet_type=packet_type_str,
            raw_bytes=data
        )

        try:
            # Decode based on packet type
            if packet_type_byte == 0xDF:
                self._decode_eeg_ppg(data, decoded)
            elif packet_type_byte == 0xF4:
                self._decode_imu(data, decoded)
            elif packet_type_byte in [0xDB, 0xD9]:
                self._decode_generic(data, decoded)
            else:
                self._decode_generic(data, decoded)

            # Calculate heart rate if we have PPG data
            if decoded.ppg and 'samples' in decoded.ppg:
                print(f"[DECODER] PPG data found: {len(decoded.ppg['samples'])} samples")
                # Add samples to processor buffer
                self.heart_rate_processor.add_ppg_samples(decoded.ppg['samples'])

                # Try to calculate heart rate
                hr = self.heart_rate_processor.calculate_heart_rate()
                if hr is not None:
                    decoded.heart_rate = hr
                    print(f"[DECODER] Heart rate calculated: {hr:.1f} BPM")

        except Exception as e:
            logger.debug(f"Decode error: {e}")
            self.stats['decode_errors'] += 1

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

    def _decode_eeg_ppg(self, data: bytes, decoded: DecodedData):
        """Decode EEG + PPG packet"""
        decoded.eeg = {}
        decoded.ppg = {}

        offset = 4  # Skip header
        channel_count = 0
        max_channels = self.config['max_channels']

        while offset < len(data) and channel_count < max_channels:
            if offset + 18 <= len(data):
                segment = data[offset:offset+18]

                # Try EEG first
                if self._looks_like_eeg(segment):
                    samples = self._unpack_eeg(segment)
                    if samples and len([s for s in samples if -500 < s < 500]) >= 4:
                        channel_name = self.config['eeg_channels'][channel_count % len(self.config['eeg_channels'])]
                        decoded.eeg[channel_name] = samples
                        self.stats['eeg_samples'] += len(samples)
                        channel_count += 1

                # Extract PPG
                ppg_samples = self._unpack_ppg_from_eeg(segment)
                print(f"[PPG EXTRACT] Found {len(ppg_samples) if ppg_samples else 0} PPG samples from segment")
                if ppg_samples:
                    if 'samples' not in decoded.ppg:
                        decoded.ppg['samples'] = []
                    decoded.ppg['samples'].extend(ppg_samples)
                    self.stats['ppg_samples'] += len(ppg_samples)
                    print(f"[PPG EXTRACT] Total PPG samples in decoded.ppg: {len(decoded.ppg['samples'])}")
                    self.heart_rate_processor.add_ppg_samples(ppg_samples)

                offset += 18
            else:
                break

    def _decode_imu(self, data: bytes, decoded: DecodedData):
        """Decode IMU packet"""
        if len(data) < 16:
            return

        decoded.imu = {}
        offset = 4

        try:
            # Unpack IMU data
            ax, ay, az, gx, gy, gz = struct.unpack_from('>hhhhhh', data, offset)

            decoded.imu['accel'] = [
                ax * self.config['imu_scale'],
                ay * self.config['imu_scale'],
                az * self.config['imu_scale']
            ]
            decoded.imu['gyro'] = [
                gx * self.config['imu_scale'],
                gy * self.config['imu_scale'],
                gz * self.config['imu_scale']
            ]
            self.stats['imu_samples'] += 2

        except Exception:
            pass

    def _decode_generic(self, data: bytes, decoded: DecodedData):
        """Generic decoder for unknown packet types"""
        offset = 0

        while offset < len(data) - 10:
            if offset + 18 <= len(data) and self._looks_like_eeg(data[offset:offset+18]):
                if decoded.eeg is None:
                    decoded.eeg = {}

                samples = self._unpack_eeg(data[offset:offset+18])
                channel_names = self.config['eeg_channels']
                ch_idx = len(decoded.eeg)
                channel_name = channel_names[ch_idx % len(channel_names)]
                decoded.eeg[channel_name] = samples
                self.stats['eeg_samples'] += len(samples)
                offset += 18
            else:
                offset += 1

    def _looks_like_eeg(self, segment: bytes) -> bool:
        """Check if segment contains EEG data"""
        if len(segment) != 18:
            return False

        sample = (segment[0] << 4) | (segment[1] >> 4)
        return 1000 < sample < 3000

    def _unpack_eeg(self, data: bytes) -> List[float]:
        """Unpack EEG samples"""
        if len(data) < 18:
            return []

        samples = []
        eeg_scale = self.config['eeg_scale']

        for i in range(6):
            offset = i * 3
            if offset + 3 > len(data):
                break

            b0, b1, b2 = data[offset:offset+3]
            sample1 = (b0 << 4) | (b1 >> 4)
            sample2 = ((b1 & 0x0F) << 8) | b2

            samples.append((sample1 - 2048) * eeg_scale)
            samples.append((sample2 - 2048) * eeg_scale)

        return samples

    def _unpack_ppg_from_eeg(self, data: bytes) -> List[int]:
        """Extract PPG data from EEG segment"""
        if len(data) < 18:
            return []

        samples = []
        min_val = self.config['ppg_range_min']
        max_val = self.config['ppg_range_max']

        # Look for PPG values in EEG segments
        for i in range(0, len(data) - 1, 2):
            val = (data[i] << 8) | data[i+1]
            if min_val <= val <= max_val:
                samples.append(val)

        return samples

    def _trigger_callbacks(self, decoded: DecodedData):
        """Trigger registered callbacks"""
        # Type-specific callbacks
        if decoded.eeg and self.callbacks['eeg']:
            for callback in self.callbacks['eeg']:
                if callback is not None:
                    callback(decoded)

        if decoded.ppg and self.callbacks['ppg']:
            for callback in self.callbacks['ppg']:
                if callback is not None:
                    callback(decoded)

        if decoded.imu and self.callbacks['imu']:
            for callback in self.callbacks['imu']:
                if callback is not None:
                    callback(decoded)

        if decoded.heart_rate and self.callbacks['heart_rate']:
            for callback in self.callbacks['heart_rate']:
                if callback is not None:
                    callback(decoded)

        # General callbacks
        for callback in self.callbacks['any']:
            if callback is not None:
                callback(decoded)

    def get_stats(self) -> Dict[str, Any]:
        """Get decoder statistics"""
        return dict(self.stats)

    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            'packets_decoded': 0,
            'eeg_samples': 0,
            'ppg_samples': 0,
            'imu_samples': 0,
            'decode_errors': 0,
            'last_packet_time': None,
        }