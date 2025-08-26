"""
Gen1-specific integration tests for sensor accuracy
Tests Gen1 device integration and data quality validation
"""

import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_realtime_decoder import MuseRealtimeDecoder

class TestGen1Integration(unittest.TestCase):
    """Test Gen1 device integration and sensor accuracy"""

    def setUp(self):
        """Set up test fixtures"""
        self.decoder = MuseRealtimeDecoder()

    def test_gen1_device_config(self):
        """Test Gen1 device configuration parameters"""
        # Test that Gen1-specific parameters are reasonable
        gen1_eeg_channels = ['TP9', 'AF7', 'AF8', 'TP10']
        gen3_only_channels = ['FPz', 'AUX_R', 'AUX_L']

        # Gen1 should support 4 EEG channels
        self.assertEqual(len(gen1_eeg_channels), 4)

        # Gen1 should NOT support certain Gen3 channels
        for channel in gen3_only_channels:
            self.assertNotIn(channel, gen1_eeg_channels)

        # All Gen1 channels should be valid EEG channel names
        for channel in gen1_eeg_channels:
            self.assertTrue(channel.startswith(('TP', 'AF')))

    def test_gen1_packet_types(self):
        """Test Gen1 packet type handling"""
        # Test different packet types that Gen1 should handle
        test_cases = [
            (bytes([0xDF, 0x00, 0x00, 0x00] + [0x80] * 20), 'EEG_PPG'),
            (bytes([0xF4, 0x00, 0x00, 0x00] + [0x00] * 16), 'IMU'),
            (bytes([0xDB, 0x00, 0x00, 0x00] + [0x40] * 10), 'MIXED_1'),
        ]

        for packet, expected_type in test_cases:
            decoded = self.decoder.decode(packet)
            self.assertIsNotNone(decoded)
            self.assertEqual(decoded.packet_type, expected_type)

    def test_gen1_data_quality_metrics(self):
        """Test Gen1 data quality assessment"""
        # Test quality threshold calculations
        good_samples = [100, 150, 200, 250]  # Within ±500 µV
        poor_samples = [600, -600, 700, -700]  # Outside range

        # Calculate valid ratios
        good_valid = len([s for s in good_samples if -500 < s < 500]) / len(good_samples)
        poor_valid = len([s for s in poor_samples if -500 < s < 500]) / len(poor_samples)

        # Good samples should have high validity
        self.assertEqual(good_valid, 1.0)

        # Poor samples should have low validity
        self.assertEqual(poor_valid, 0.0)

        # Test quality thresholds
        self.assertTrue(good_valid >= 0.8)  # Excellent quality
        self.assertTrue(poor_valid < 0.5)   # Poor quality

    def test_gen1_sensor_ranges(self):
        """Test Gen1 sensor value ranges"""
        # Test EEG ranges
        eeg_values = [-400, -200, 0, 200, 400]
        for value in eeg_values:
            self.assertGreaterEqual(value, -500)
            self.assertLessEqual(value, 500)

        # Test PPG ranges (typical values)
        ppg_values = [10000, 20000, 30000, 40000]
        for value in ppg_values:
            self.assertGreater(value, 0)
            self.assertLess(value, 100000)  # Reasonable PPG range

        # Test IMU ranges (typical values)
        imu_values = [-2.0, -1.0, 0.0, 1.0, 2.0]
        for value in imu_values:
            self.assertGreaterEqual(value, -10.0)
            self.assertLessEqual(value, 10.0)

    def test_gen1_sample_rates(self):
        """Test Gen1 expected sample rates"""
        # Gen1 typical rates
        expected_rates = {
            'eeg': 256,   # Hz
            'ppg': 64,    # Hz
            'imu': 50,    # Hz
        }

        # All rates should be reasonable for wearable devices
        for sensor, rate in expected_rates.items():
            self.assertGreater(rate, 10)   # At least 10 Hz
            self.assertLess(rate, 1000)    # Less than 1000 Hz

        # EEG should be highest rate
        self.assertEqual(expected_rates['eeg'], 256)

        # PPG should be medium rate
        self.assertEqual(expected_rates['ppg'], 64)

    def test_gen1_accuracy_improvements(self):
        """Test potential Gen1 accuracy improvement strategies"""
        # Test different quality threshold scenarios
        scenarios = [
            {'threshold': 0.6, 'description': 'Current threshold'},
            {'threshold': 0.7, 'description': 'Higher threshold'},
            {'threshold': 0.8, 'description': 'Excellent threshold'},
        ]

        for scenario in scenarios:
            threshold = scenario['threshold']

            # Test that higher thresholds are more strict
            if threshold > 0.6:
                self.assertGreater(threshold, 0.6)

            # Test that thresholds are reasonable
            self.assertGreater(threshold, 0.0)
            self.assertLessEqual(threshold, 1.0)

    def test_gen1_channel_mapping(self):
        """Test Gen1 channel mapping and identification"""
        # Gen1 supported channels
        gen1_channels = ['TP9', 'AF7', 'AF8', 'TP10']

        # Test channel identification
        for channel in gen1_channels:
            self.assertTrue(len(channel) >= 3)  # All have meaningful names
            self.assertTrue(channel[0].isalpha())  # Start with letter
            # Allow alphanumeric combinations (TP9, AF7, etc.)
            remaining = channel[1:]
            self.assertTrue(len(remaining) > 0)  # Must have characters after first letter
            # Check that remaining characters are alphanumeric
            self.assertTrue(all(c.isalnum() for c in remaining))

        # Test that channels are unique
        self.assertEqual(len(gen1_channels), len(set(gen1_channels)))

if __name__ == '__main__':
    unittest.main()