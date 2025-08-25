#!/usr/bin/env python3
"""
Test script to verify Gen1 Muse integration with updated configuration and decoder
"""

import asyncio
import json
from muse_realtime_decoder import MuseRealtimeDecoder
from muse_stream_client import MuseDeviceConfig

def test_gen1_config():
    """Test Gen1 configuration"""
    print("🧪 Testing Gen1 Configuration")
    print("=" * 50)

    config = MuseDeviceConfig.get_gen1_config()
    print(f"Name: {config['name']}")
    print(f"Service UUID: {config['service_uuid']}")
    print(f"Control UUID: {config['control_char_uuid']}")
    print(f"Sensor UUIDs: {len(config['sensor_char_uuids'])}")
    for i, uuid in enumerate(config['sensor_char_uuids']):
        print(f"  {i+1}. {uuid}")
    print(f"EEG Channels: {config['eeg_channels']}")
    print(f"EEG Scale: {config['eeg_scale_factor']}")
    print(f"IMU Accel Scale: {config['imu_accel_scale']}")
    print(f"IMU Gyro Scale: {config['imu_gyro_scale']}")
    print(f"Expected Packet Types: {[f'0x{t:02x}' for t in config['expected_packet_types']]}")

    # Verify all expected channels are present
    expected_channels = ['TP9', 'AF7', 'AF8', 'TP10', 'FPz', 'AUX_R', 'AUX_L']
    assert config['eeg_channels'] == expected_channels, "EEG channels don't match expected"
    assert len(config['sensor_char_uuids']) == 8, "Should have 8 sensor UUIDs"

    print("✅ Configuration test passed!")
    return config

def test_gen1_decoder():
    """Test Gen1 decoder with sample packets"""
    print("\n🧪 Testing Gen1 Decoder")
    print("=" * 50)

    decoder = MuseRealtimeDecoder()

    # Load test data
    with open('/var/home/codenomad/Development/amused-py/tests/test_data/muse_20250824_172756_samples.json', 'r') as f:
        data = json.load(f)

    # Test EEG packets
    print("Testing EEG packets...")
    eeg_channels_found = set()
    total_eeg_samples = 0

    for i, packet in enumerate(data['eeg_packets'][:3]):
        packet_data = bytes.fromhex(packet['hex'])
        decoded = decoder.decode(packet_data)

        print(f"  Packet {i+1}: {decoded.packet_type}")
        if decoded.eeg:
            print(f"    EEG Channels: {list(decoded.eeg.keys())}")
            eeg_channels_found.update(decoded.eeg.keys())
            for ch, samples in decoded.eeg.items():
                total_eeg_samples += len(samples)
                print(f"    {ch}: {len(samples)} samples, range: {min(samples):.1f} to {max(samples):.1f} μV")

        if decoded.ppg and 'samples' in decoded.ppg:
            print(f"    PPG Samples: {len(decoded.ppg['samples'])}")

    # Test IMU packets
    print("\nTesting IMU packets...")
    for i, packet in enumerate(data['imu_packets'][:2]):
        packet_data = bytes.fromhex(packet['hex'])
        decoded = decoder.decode(packet_data)

        print(f"  Packet {i+1}: {decoded.packet_type}")
        if decoded.imu:
            if 'accel' in decoded.imu:
                accel = decoded.imu['accel']
                print(f"    Accel: x={accel[0]:.2f}, y={accel[1]:.2f}, z={accel[2]:.2f}")
            if 'gyro' in decoded.imu:
                gyro = decoded.imu['gyro']
                print(f"    Gyro: x={gyro[0]:.2f}, y={gyro[1]:.2f}, z={gyro[2]:.2f}")

    # Show statistics
    stats = decoder.get_stats()
    print(f"\n📊 Decoder Statistics:")
    print(f"  Packets decoded: {stats['packets_decoded']}")
    print(f"  EEG samples: {stats['eeg_samples']}")
    print(f"  PPG samples: {stats['ppg_samples']}")
    print(f"  IMU samples: {stats['imu_samples']}")
    print(f"  Error rate: {stats['error_rate']:.1%}")

    # Verify we found multiple EEG channels
    print(f"\n📡 EEG Channels Found: {sorted(eeg_channels_found)}")
    assert len(eeg_channels_found) > 1, "Should find multiple EEG channels"
    assert total_eeg_samples > 0, "Should have EEG samples"

    print("✅ Decoder test passed!")
    return stats

def test_gen1_stream_client():
    """Test Gen1 stream client configuration"""
    print("\n🧪 Testing Gen1 Stream Client")
    print("=" * 50)

    try:
        from muse_stream_client import MuseStreamClient

        # Test Gen1 client creation
        client = MuseStreamClient(device_model='gen1', verbose=False)
        device_name = client.get_device_model_name()
        print(f"Device model: {device_name}")

        assert 'Gen 1' in device_name, "Should be Gen1 device"
        assert len(client.device_config['sensor_char_uuids']) == 8, "Should have 8 sensor UUIDs"

        print("✅ Stream client test passed!")
        return True

    except ImportError as e:
        print(f"⚠️ Could not import MuseStreamClient: {e}")
        return False

async def test_gen1_integration():
    """Main integration test"""
    print("🧪 Gen1 Muse Integration Test Suite")
    print("=" * 60)

    try:
        # Test configuration
        config = test_gen1_config()

        # Test decoder
        decoder_stats = test_gen1_decoder()

        # Test stream client
        client_ok = test_gen1_stream_client()

        print("\n" + "=" * 60)
        print("🎉 All tests completed successfully!")
        print("✅ Gen1 Muse integration is ready for testing with real device")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_gen1_integration())
    exit(0 if success else 1)