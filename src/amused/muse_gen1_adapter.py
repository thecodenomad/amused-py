"""
Muse S Gen 1 Adapter
Adapts the Gen 3 (Athena) implementation for Gen 1 compatibility

Based on analysis of protocol differences between Muse generations.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import struct

@dataclass
class Gen1Config:
    """Configuration for Muse S Gen 1 specific settings"""
    # BLE UUIDs - may differ from Gen 3
    service_uuid: str = "0000fe8d-0000-1000-8000-00805f9b34fb"  # Same as Gen 3?
    control_char_uuid: str = "273e0001-4c4d-454d-96be-f03bac821358"  # Same?
    sensor_char_uuids: Optional[List[str]] = None  # Will be set in __post_init__

    def __post_init__(self):
        if self.sensor_char_uuids is None:
            self.sensor_char_uuids = [
                "273e0013-4c4d-454d-96be-f03bac821358",  # Combined sensors
                "273e0003-4c4d-454d-96be-f03bac821358",  # EEG TP9
            ]
        if self.commands is None:
            self.commands = {
                'v1': bytes.fromhex('0376310a'),           # Version (Gen 1 style)
                'v6': bytes.fromhex('0376360a'),           # Version (Gen 3 style)
                's': bytes.fromhex('02730a'),              # Status
                'h': bytes.fromhex('02680a'),              # Halt
                'p21': bytes.fromhex('047032310a'),        # Basic preset
                'p1034': bytes.fromhex('0670313033340a'),  # Sleep preset
                'dc001': bytes.fromhex('0664633030310a'),  # Start streaming
                'L1': bytes.fromhex('034c310a'),           # L1 command
            }
        if self.expected_packet_types is None:
            self.expected_packet_types = [0xDF, 0xF4, 0xDB, 0xD9]
        if self.eeg_channels is None:
            self.eeg_channels = ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']

    # Command sequences - may need adjustment for Gen 1
    commands: Optional[Dict[str, bytes]] = None  # Will be set in __post_init__

    # Data format settings - may differ from Gen 3
    eeg_scale_factor: float = 0.48828125  # May need adjustment
    imu_accel_scale: float = 2.0 / 32768.0
    imu_gyro_scale: float = 250.0 / 32768.0

    # Packet structure - may differ from Gen 3
    expected_packet_types: Optional[List[int]] = None  # Will be set in __post_init__
    eeg_channels: Optional[List[str]] = None  # Will be set in __post_init__

class MuseGen1Adapter:
    """
    Adapter to make the Gen 3 implementation work with Muse S Gen 1

    This class provides Gen 1 specific modifications and can be used to
    override Gen 3 behavior when working with older hardware.
    """

    def __init__(self, config: Optional[Gen1Config] = None):
        self.config = config or Gen1Config()
        self.detected_differences = []
        self.adaptation_mode = True

    def adapt_command_sequence(self, commands: List[str]) -> List[bytes]:
        """
        Adapt command sequence for Gen 1

        Args:
            commands: List of command names (e.g., ['v6', 's', 'h', 'p1034'])

        Returns:
            List of command bytes adapted for Gen 1
        """
        adapted = []
        for cmd in commands:
            if cmd in self.config.commands:
                adapted.append(self.config.commands[cmd])
            else:
                print(f"⚠️ Unknown command: {cmd}")
                adapted.append(cmd.encode())  # Fallback

        return adapted

    def adapt_packet_parsing(self, data: bytes) -> Dict[str, Any]:
        """
        Adapt packet parsing for Gen 1 format

        This method can be modified based on actual Gen 1 packet captures
        """
        result = {
            'packet_type': 'unknown',
            'adapted': True,
            'original_data': data.hex()
        }

        if len(data) == 0:
            return result

        packet_type = data[0]

        # Check if packet type matches expected Gen 3 types
        if packet_type in self.config.expected_packet_types:
            result['packet_type'] = f'0x{packet_type:02x}'
            result['matches_gen3'] = True
        else:
            result['packet_type'] = f'0x{packet_type:02x}'
            result['matches_gen3'] = False
            result['difference'] = 'unexpected_packet_type'
            self.detected_differences.append({
                'type': 'packet_type',
                'expected': self.config.expected_packet_types,
                'actual': packet_type,
                'data': data.hex()[:50]
            })

        # Try to parse based on packet length (common Gen 1 pattern)
        if len(data) == 20:  # Standard BLE packet size
            result['structure'] = 'standard_20_byte'
            self._parse_standard_packet(data, result)
        elif len(data) == 18:  # Possible EEG segment
            result['structure'] = 'possible_eeg_18_byte'
            self._parse_eeg_segment(data, result)
        else:
            result['structure'] = f'unusual_length_{len(data)}'

        return result

    def _parse_standard_packet(self, data: bytes, result: Dict):
        """Parse standard 20-byte packet (may differ from Gen 3)"""
        try:
            # Try Gen 3 format first
            counter = struct.unpack('>H', data[0:2])[0]

            # Check if this looks like EEG data
            if 0 < counter < 65535:
                samples = self._unpack_eeg_samples_gen1(data[2:20])
                if samples:
                    result['eeg_samples'] = samples
                    result['counter'] = counter
                    result['parsing_method'] = 'gen3_compatible'
                else:
                    result['parsing_method'] = 'gen3_format_but_no_samples'
            else:
                result['parsing_method'] = 'unexpected_counter_value'

        except Exception as e:
            result['parsing_error'] = str(e)
            result['parsing_method'] = 'failed'

    def _parse_eeg_segment(self, data: bytes, result: Dict):
        """Parse 18-byte EEG segment (may differ from Gen 3)"""
        try:
            samples = self._unpack_eeg_samples_gen1(data)
            if samples:
                result['eeg_samples'] = samples
                result['parsing_method'] = 'eeg_segment_success'
            else:
                result['parsing_method'] = 'eeg_segment_no_samples'
        except Exception as e:
            result['parsing_error'] = str(e)
            result['parsing_method'] = 'eeg_segment_failed'

    def _unpack_eeg_samples_gen1(self, data: bytes) -> List[float]:
        """
        Unpack EEG samples for Gen 1

        This may need to be different from Gen 3 if the bit packing changed
        """
        if len(data) < 18:
            return []

        samples = []
        try:
            # Try Gen 3 format first (12-bit samples in 18 bytes)
            for i in range(6):  # 6 groups of 3 bytes = 2 samples
                offset = i * 3
                if offset + 3 <= len(data):
                    three_bytes = data[offset:offset+3]

                    # Extract two 12-bit samples from 3 bytes
                    sample1 = (three_bytes[0] << 4) | (three_bytes[1] >> 4)
                    sample2 = ((three_bytes[1] & 0x0F) << 8) | three_bytes[2]

                    # Convert to microvolts
                    uv1 = (sample1 - 2048) * self.config.eeg_scale_factor
                    uv2 = (sample2 - 2048) * self.config.eeg_scale_factor

                    # Sanity check
                    if -500 < uv1 < 500:
                        samples.append(uv1)
                    if -500 < uv2 < 500:
                        samples.append(uv2)

        except Exception as e:
            print(f"⚠️ EEG unpacking error: {e}")

        return samples

    def get_adaptation_report(self) -> Dict[str, Any]:
        """Get report on adaptations made and differences detected"""
        return {
            'adaptation_mode': self.adaptation_mode,
            'detected_differences': self.detected_differences,
            'config': {
                'service_uuid': self.config.service_uuid,
                'control_char_uuid': self.config.control_char_uuid,
                'sensor_char_uuids': self.config.sensor_char_uuids,
                'commands': {k: v.hex() for k, v in self.config.commands.items()},
                'eeg_scale_factor': self.config.eeg_scale_factor,
                'expected_packet_types': [f'0x{t:02x}' for t in self.config.expected_packet_types]
            },
            'differences_count': len(self.detected_differences)
        }

# Convenience functions for Gen 1 testing
def create_gen1_test_config() -> Gen1Config:
    """Create a test configuration for Gen 1"""
    return Gen1Config()

def test_gen1_packet_parsing():
    """Test packet parsing with sample data"""
    adapter = MuseGen1Adapter()

    # Test with sample packet (this would come from your device)
    test_packets = [
        bytes.fromhex("df0000a1dae289930111059c010084407640570cf993a8e0fa3e1752ffffffffff03003edd3798116f82"),
        bytes.fromhex("f40200" + "0100020003000400050006" * 2),
    ]

    print("🧪 Testing Gen 1 Packet Parsing")
    print("=" * 50)

    for i, packet in enumerate(test_packets):
        print(f"\n📦 Test Packet {i+1}:")
        print(f"   Raw: {packet.hex()}")
        print(f"   Length: {len(packet)} bytes")

        result = adapter.adapt_packet_parsing(packet)

        print(f"   Type: {result['packet_type']}")
        print(f"   Structure: {result['structure']}")
        print(f"   Parsing: {result['parsing_method']}")

        if 'eeg_samples' in result:
            print(f"   EEG Samples: {len(result['eeg_samples'])}")
            print(f"   Sample Values: {result['eeg_samples'][:3]}")

    # Show adaptation report
    report = adapter.get_adaptation_report()
    print("\n📊 Adaptation Report:")
    print(f"   Differences Detected: {report['differences_count']}")
    if report['detected_differences']:
        print("   Differences:")
        for diff in report['detected_differences']:
            print(f"     - {diff['type']}: {diff['actual']} (expected {diff['expected']})")

if __name__ == "__main__":
    test_gen1_packet_parsing()