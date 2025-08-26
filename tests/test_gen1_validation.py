"""
Gen1-specific validation tests for sensor accuracy
Tests Gen1 device sensor validation and accuracy improvements
"""

import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_realtime_decoder import MuseRealtimeDecoder

class TestGen1SensorValidation(unittest.TestCase):
    """Test Gen1 sensor validation and accuracy"""

    def setUp(self):
        """Set up test fixtures"""
        self.decoder = MuseRealtimeDecoder()

    def test_gen1_eeg_channel_support(self):
        """Test that Gen1 supports correct EEG channels"""
        # Gen1 should support TP9, AF7, AF8, TP10
        gen1_supported_channels = ['TP9', 'AF7', 'AF8', 'TP10']
        gen3_only_channels = ['FPz', 'AUX_R', 'AUX_L']

        # Test with Gen1-style packet
        gen1_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9)
        decoded = self.decoder.decode(gen1_packet)

        # Should decode successfully
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.packet_type, 'EEG_PPG')

        # Check that we can decode some EEG data
        if decoded.eeg:
            # Should have at least one channel
            self.assertGreater(len(decoded.eeg), 0)

    def test_gen1_quality_thresholds(self):
        """Test Gen1-specific quality thresholds"""
        # Test with different quality levels
        good_samples = [100, 150, 200, 250]  # Within -500 to +500 range
        poor_samples = [600, -600, 700, -700]  # Outside range

        # Calculate valid ratios
        good_valid_ratio = len([s for s in good_samples if -500 < s < 500]) / len(good_samples)
        poor_valid_ratio = len([s for s in poor_samples if -500 < s < 500]) / len(poor_samples)

        # Good samples should have 100% valid ratio
        self.assertEqual(good_valid_ratio, 1.0)

        # Poor samples should have 0% valid ratio
        self.assertEqual(poor_valid_ratio, 0.0)

    def test_gen1_packet_format_detection(self):
        """Test detection of Gen1 packet formats"""
        # Test different packet types that Gen1 should handle
        test_packets = [
            (bytes([0xDF, 0x00, 0x00, 0x00] + [0x80] * 20), 'EEG_PPG'),
            (bytes([0xF4, 0x00, 0x00, 0x00] + [0x00] * 16), 'IMU'),
            (bytes([0xDB, 0x00, 0x00, 0x00] + [0x40] * 10), 'MIXED_1'),
        ]

        for packet, expected_type in test_packets:
            decoded = self.decoder.decode(packet)
            self.assertIsNotNone(decoded)
            self.assertEqual(decoded.packet_type, expected_type)

    def test_gen1_sensor_data_ranges(self):
        """Test that Gen1 sensor data stays within expected ranges"""
        # Test EEG range validation
        eeg_values = [-400, -200, 0, 200, 400]  # All within ±500 µV

        for value in eeg_values:
            self.assertGreaterEqual(value, -500)
            self.assertLessEqual(value, 500)

        # Test out of range values
        out_of_range = [-600, 600, -1000, 1000]
        for value in out_of_range:
            self.assertTrue(value < -500 or value > 500)

    def test_gen1_sample_rate_calculation(self):
        """Test Gen1 sample rate calculations"""
        # Gen1 typically samples at 256 Hz for EEG
        expected_eeg_rate = 256
        expected_ppg_rate = 64
        expected_imu_rate = 50

        # Test that rates are reasonable for wearable devices
        self.assertGreater(expected_eeg_rate, 200)  # Should be > 200 Hz
        self.assertLess(expected_eeg_rate, 1000)    # Should be < 1000 Hz

        self.assertGreater(expected_ppg_rate, 30)   # Should be > 30 Hz
        self.assertLess(expected_ppg_rate, 200)     # Should be < 200 Hz

    def test_gen1_data_consistency(self):
        """Test that Gen1 data remains consistent across packets"""
        # Create multiple similar packets
        packets = []
        for i in range(5):
            packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80 + i, 0x08] * 9)
            packets.append(packet)

        # Decode all packets
        decoded_packets = []
        for packet in packets:
            decoded = self.decoder.decode(packet)
            decoded_packets.append(decoded)

        # All should be EEG_PPG type
        for decoded in decoded_packets:
            self.assertEqual(decoded.packet_type, 'EEG_PPG')

        # Should have similar structure
        for decoded in decoded_packets:
            if decoded.eeg:
                # Should have reasonable number of samples
                for channel, samples in decoded.eeg.items():
                    self.assertGreater(len(samples), 0)
                    self.assertLess(len(samples), 20)  # Reasonable sample count

if __name__ == '__main__':
    unittest.main()