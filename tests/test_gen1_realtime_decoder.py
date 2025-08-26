"""
Gen1-specific tests for Muse Real-time Decoder
Tests Gen1 packet decoding with Gen1-specific formats and validation
"""

import unittest
import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muse_realtime_decoder import MuseRealtimeDecoder, DecodedData
from muse_gen1_adapter import MuseGen1Adapter

class TestGen1RealtimeDecoder(unittest.TestCase):
    """Test real-time packet decoding for Gen1 devices"""

    def setUp(self):
        """Set up test fixtures"""
        self.decoder = MuseRealtimeDecoder()
        self.gen1_adapter = MuseGen1Adapter()

    def test_gen1_eeg_packet_decoding(self):
        """Test Gen1 EEG packet decoding with adapter"""
        # Create a mock Gen1 EEG packet (different format from Gen3)
        # Gen1 packets may have different structure
        gen1_packet = bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9)

        # Test with Gen1 adapter
        adapted = self.gen1_adapter.adapt_packet_parsing(gen1_packet)
        decoded = self.decoder.decode(gen1_packet)

        self.assertEqual(decoded.packet_type, 'EEG_PPG')
        self.assertIsNotNone(decoded.eeg)
        # Gen1 should support TP9, AF7, AF8, TP10
        expected_channels = ['TP9', 'AF7', 'AF8', 'TP10']
        for channel in expected_channels:
            if channel in decoded.eeg:
                self.assertGreater(len(decoded.eeg[channel]), 0)

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
        """Test Gen1 adapter integration with decoder"""
        test_packets = [
            bytes([0xDF, 0x00, 0x00, 0x00] + [0x80, 0x08] * 9),
            bytes([0xF4, 0x00, 0x00, 0x00] + [0x00, 0x64] * 6),
            bytes([0xDB, 0x00, 0x00, 0x00] + [0x40, 0x20] * 5),
        ]

        for packet in test_packets:
            adapted = self.gen1_adapter.adapt_packet_parsing(packet)
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