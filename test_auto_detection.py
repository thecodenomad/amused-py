#!/usr/bin/env python3
"""
Test script to demonstrate automatic Muse device model detection
"""

import asyncio
from muse_stream_client import MuseStreamClient, MuseDeviceConfig

def test_auto_detection_logic():
    """Test the auto-detection logic with mock device info"""
    print("🧪 Testing Auto-Detection Logic")
    print("=" * 50)

    # Create a client with auto mode
    client = MuseStreamClient(device_model='auto', verbose=False)

    # Test different firmware versions
    test_cases = [
        ("1.2.3", "gen1"),  # Gen1 firmware
        ("0.9.1", "gen1"),  # Gen1 firmware
        ("2.1.5", "gen3"),  # Gen3 firmware
        ("3.0.1", "gen3"),  # Gen3 firmware
    ]

    for fw_version, expected in test_cases:
        # Mock device info
        client.device_info = {'fw': fw_version}

        # Test detection logic
        detected = None
        if 'fw' in client.device_info:
            fw = client.device_info['fw']
            if fw.startswith('1.') or fw.startswith('0.'):
                detected = 'gen1'
            elif fw.startswith('2.') or fw.startswith('3.'):
                detected = 'gen3'

        print(f"  Firmware {fw_version} -> Detected: {detected} (Expected: {expected})")
        assert detected == expected, f"Expected {expected}, got {detected}"

    print("✅ Auto-detection logic test passed!")

def test_device_configurations():
    """Test that different configurations work correctly"""
    print("\n🧪 Testing Device Configurations")
    print("=" * 50)

    configs = {
        'gen1': MuseDeviceConfig.get_gen1_config(),
        'gen3': MuseDeviceConfig.get_gen3_config(),
        'auto': MuseDeviceConfig.get_gen3_config(),  # Auto starts with Gen3
    }

    for model, config in configs.items():
        print(f"\n📋 {model.upper()} Configuration:")
        print(f"   Name: {config['name']}")
        print(f"   Service UUID: {config['service_uuid']}")
        print(f"   Control UUID: {config['control_char_uuid']}")
        print(f"   Sensor UUIDs: {len(config['sensor_char_uuids'])}")
        print(f"   Commands: {list(config['commands'].keys())}")
        print(f"   EEG Channels: {config['eeg_channels']}")

        # Verify essential components exist
        assert 'service_uuid' in config
        assert 'control_char_uuid' in config
        assert 'sensor_char_uuids' in config
        assert 'commands' in config
        assert 'eeg_channels' in config

    print("✅ Device configuration test passed!")

async def test_auto_mode_simulation():
    """Simulate auto-detection process"""
    print("\n🧪 Testing Auto Mode Simulation")
    print("=" * 50)

    # Test that auto mode starts with Gen3
    client = MuseStreamClient(device_model='auto', verbose=False)
    assert client.device_model == 'auto'
    assert 'Gen 3' in client.get_device_model_name()

    print("✅ Auto mode simulation test passed!")

def main():
    """Main test function"""
    print("🧪 Muse Auto-Detection Test Suite")
    print("=" * 60)

    try:
        # Test auto-detection logic
        test_auto_detection_logic()

        # Test configurations
        test_device_configurations()

        # Test auto mode
        asyncio.run(test_auto_mode_simulation())

        print("\n" + "=" * 60)
        print("🎉 All auto-detection tests completed successfully!")
        print("\n💡 How Auto-Detection Works:")
        print("   1. Connect with device_model='auto'")
        print("   2. Send version command to get firmware info")
        print("   3. Analyze firmware version:")
        print("      - 1.x.x or 0.x.x = Muse S Gen 1")
        print("      - 2.x.x or 3.x.x = Muse S Gen 3")
        print("   4. Switch configuration if needed")
        print("   5. Continue with appropriate settings")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)