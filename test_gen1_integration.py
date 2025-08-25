#!/usr/bin/env python3
"""
Test script to demonstrate Gen 1 integration in muse_stream_client.py
"""

import asyncio
from muse_stream_client import MuseStreamClient, MuseDeviceConfig

async def test_gen1_integration():
    """Test the Gen 1 integration"""
    print("🧪 Testing Gen 1 Integration in MuseStreamClient")
    print("=" * 60)

    # Test Gen 1 configuration
    print("\n📋 Testing Gen 1 Configuration:")
    gen1_config = MuseDeviceConfig.get_gen1_config()
    print(f"   Name: {gen1_config['name']}")
    print(f"   Service UUID: {gen1_config['service_uuid']}")
    print(f"   Commands: {list(gen1_config['commands'].keys())}")
    print(f"   Packet Types: {gen1_config['expected_packet_types']}")

    # Test Gen 3 configuration
    print("\n📋 Testing Gen 3 Configuration:")
    gen3_config = MuseDeviceConfig.get_gen3_config()
    print(f"   Name: {gen3_config['name']}")
    print(f"   Service UUID: {gen3_config['service_uuid']}")
    print(f"   Commands: {list(gen3_config['commands'].keys())}")
    print(f"   Packet Types: {gen3_config['expected_packet_types']}")

    # Test client with Gen 1
    print("\n🤖 Testing MuseStreamClient with Gen 1:")
    client_gen1 = MuseStreamClient(device_model='gen1', verbose=False)
    print(f"   Device Model: {client_gen1.get_device_model_name()}")
    print(f"   Control UUID: {client_gen1.device_config['control_char_uuid']}")
    print(f"   Available Commands: {list(client_gen1.device_config['commands'].keys())}")

    # Test client with Gen 3
    print("\n🤖 Testing MuseStreamClient with Gen 3:")
    client_gen3 = MuseStreamClient(device_model='gen3', verbose=False)
    print(f"   Device Model: {client_gen3.get_device_model_name()}")
    print(f"   Control UUID: {client_gen3.device_config['control_char_uuid']}")
    print(f"   Available Commands: {list(client_gen3.device_config['commands'].keys())}")

    # Test auto mode
    print("\n🤖 Testing MuseStreamClient with Auto mode:")
    client_auto = MuseStreamClient(device_model='auto', verbose=False)
    print(f"   Device Model: {client_auto.get_device_model_name()}")
    print(f"   Control UUID: {client_auto.device_config['control_char_uuid']}")

    print("\n✅ Gen 1 Integration Test Complete!")
    print("\n💡 To use with your Muse S Gen 1 device:")
    print("   client = MuseStreamClient(device_model='gen1')")
    print("   await client.connect_and_stream(device_address, duration_seconds=30)")

if __name__ == "__main__":
    asyncio.run(test_gen1_integration())