"""
Muse Device Configurations
Centralized configuration for different Muse device generations
"""

from typing import Dict, Any


class MuseDeviceConfig:
    """Configuration for different Muse device generations"""

    @staticmethod
    def get_gen1_config() -> Dict[str, Any]:
        """Configuration for Muse S Gen 1"""
        return {
            'name': 'Muse S Gen 1',
            'service_uuid': "0000fe8d-0000-1000-8000-00805f9b34fb",
            'control_char_uuid': "273e0001-4c4d-454d-96be-f03bac821358",
            'sensor_char_uuids': [
                "273e0003-4c4d-454d-96be-f03bac821358",  # EEG TP9
                "273e0004-4c4d-454d-96be-f03bac821358",  # EEG AF7
                "273e0005-4c4d-454d-96be-f03bac821358",  # EEG AF8
                "273e0006-4c4d-454d-96be-f03bac821358",  # EEG TP10
                "273e0008-4c4d-454d-96be-f03bac821358",  # IMU
                "273e0009-4c4d-454d-96be-f03bac821358",  # PPG
                "273e000a-4c4d-454d-96be-f03bac821358",  # PPG
            ],
            'commands': {
                'v1': bytes.fromhex('0376310a'),
                'v6': bytes.fromhex('0376360a'),
                's': bytes.fromhex('02730a'),
                'h': bytes.fromhex('02680a'),
                'p21': bytes.fromhex('047032310a'),
                'p22': bytes.fromhex('047032320a'),
                'p23': bytes.fromhex('047032330a'),
                'p1034': bytes.fromhex('0670313033340a'),
                'p1035': bytes.fromhex('0670313033350a'),
                'p1036': bytes.fromhex('0670313033360a'),
                'dc001': bytes.fromhex('0664633030310a'),
                'L1': bytes.fromhex('034c310a'),
            },
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
            'sampling_rate': 16.0,
            'stabilization_time': 5.0,
            'eeg_channels': ['TP9', 'AF7', 'AF8', 'TP10'],
            'max_channels': 4,
        }

    @staticmethod
    def get_gen3_config() -> Dict[str, Any]:
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
                'v6': bytes.fromhex('0376360a'),
                's': bytes.fromhex('02730a'),
                'h': bytes.fromhex('02680a'),
                'p21': bytes.fromhex('047032310a'),
                'p1034': bytes.fromhex('0670313033340a'),
                'p1035': bytes.fromhex('0670313033350a'),
                'dc001': bytes.fromhex('0664633030310a'),
                'L1': bytes.fromhex('034c310a'),
            },
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


def get_device_config(device_model: str) -> Dict[str, Any]:
    """Get configuration for specified device model"""
    if device_model == 'gen1':
        return MuseDeviceConfig.get_gen1_config()
    elif device_model == 'gen3':
        return MuseDeviceConfig.get_gen3_config()
    elif device_model == 'auto':
        # For auto-detection, default to Gen1 (more common)
        return MuseDeviceConfig.get_gen1_config()
    else:
        raise ValueError(f"Unknown device model: {device_model}")


def detect_device_model_from_name(device_name: str) -> str:
    """Detect device model from device name"""
    if device_name and 'MuseS-' in device_name:
        return 'gen1'
    elif device_name and 'Muse-' in device_name:
        return 'gen3'
    else:
        return 'gen3'  # Default fallback