"""
Gen1-specific tests for Muse Real-time Decoder
Tests Gen1 packet decoding with Gen1-specific formats and validation
"""

import unittest
import datetime
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from amused.muse_decoder import MuseRealtimeDecoder, DecodedData

class TestGen1RealtimeDecoder(unittest.TestCase):
    """Test real-time packet decoding for Gen1 devices"""

    def setUp(self):
        """Set up test fixtures"""
        self.decoder = MuseRealtimeDecoder('gen1')

    def test_gen1_eeg_packet_decoding(self):
        """Test Gen1 EEG packet decoding"""
        # Create a mock Gen1 EEG packet with proper EEG data
        # EEG data should have values around 2048 (baseline) ± some variation
        eeg_values = [2100, 1900, 2050, 2150, 2000, 2080]  # 6 samples * 2 bytes each = 12 bytes
        eeg_bytes = b''.join(val.to_bytes(2, 'big') for val in eeg_values)
        gen1_packet = bytes([0xDF, 0x00, 0x00, 0x00]) + eeg_bytes

        decoded = self.decoder.decode(gen1_packet)

        self.assertEqual(decoded.packet_type, 'EEG_PPG')
        self.assertIsNotNone(decoded.eeg)
        # Check that we got some EEG data
        if decoded.eeg:
            total_samples = sum(len(samples) for samples in decoded.eeg.values())
            self.assertGreater(total_samples, 0)

    def test_gen1_quality_validation(self):
        """Test Gen1-specific quality validation"""
        # Create packets with varying quality
        good_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9)
        poor_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0xFF, 0xFF] * 9)  # Out of range

        good_decoded = self.decoder.decode(good_packet)
        poor_decoded = self.decoder.decode(poor_packet)

        # Check that valid samples are identified
        if good_decoded.eeg:
            for channel, samples in good_decoded.eeg.items():
                valid_samples = [s for s in samples if -500 < s < 500]
                valid_ratio = len(valid_samples) / len(samples) if samples else 0
                self.assertGreaterEqual(valid_ratio, 0.5, f"Channel {channel} should have >=50% valid samples")

    def test_gen1_adapter_integration(self):
        """Test Gen1 decoder with various packet types"""
        test_packets = [
            bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9),
            bytes([0xF4, 0x00, 0x00, 0x00] + [0x00, 0x64] * 6),
            bytes([0xDB, 0x00, 0x00, 0x00] + [0x40, 0x20] * 5),
        ]

        for packet in test_packets:
            decoded = self.decoder.decode(packet)

            # Should not crash and should produce valid results
            self.assertIsNotNone(decoded)
            self.assertIsInstance(decoded, DecodedData)

    def test_gen1_callback_system(self):
        """Test callback system with Gen1 packets"""
        eeg_called = False
        gen1_packets = []

        def on_eeg(data: DecodedData):
            nonlocal eeg_called, gen1_packets
            eeg_called = True
            gen1_packets.append(data)

        self.decoder.register_callback('eeg', on_eeg)

        # Decode Gen1-style packets
        gen1_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9)
        self.decoder.decode(gen1_packet)

        self.assertTrue(eeg_called)
        self.assertGreater(len(gen1_packets), 0)

    def test_gen1_statistics_tracking(self):
        """Test statistics tracking with Gen1 packets"""
        self.decoder.reset_stats()

        # Decode various Gen1 packet types
        packets = [
            bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9),  # EEG
            bytes([0xF4, 0x00, 0x00, 0x00] + [0x00, 0x64] * 6),  # IMU
            bytes([0xDB, 0x00, 0x00, 0x00] + [0x40, 0x20] * 5),  # Mixed
        ]

        for packet in packets:
            self.decoder.decode(packet)

        stats = self.decoder.get_stats()

        self.assertEqual(stats['packets_decoded'], 3)
        self.assertGreater(stats['eeg_samples'], 0)
        self.assertEqual(stats['decode_errors'], 0)

if __name__ == '__main__':
    unittest.main()