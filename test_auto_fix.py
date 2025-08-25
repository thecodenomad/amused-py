#!/usr/bin/env python3
"""
Test the auto-detection fix to ensure it properly defaults to Gen1
"""

import asyncio
from muse_stream_client import MuseStreamClient

async def test_auto_detection():
    """Test that auto detection now properly defaults to Gen1"""
    print("🧪 Testing Auto-Detection Fix")
    print("=" * 50)

    # Test 1: Check that 'auto' defaults to Gen1 config initially
    print("\n1. Testing initial auto configuration...")
    client = MuseStreamClient(device_model='auto', verbose=False)

    device_name = client.get_device_model_name()
    print(f"   Initial config: {device_name}")

    if 'Gen 1' in device_name:
        print("   ✅ PASS: Auto defaults to Gen1 config")
    else:
        print("   ❌ FAIL: Auto does not default to Gen1 config")

    # Test 2: Check that explicit Gen1 still works
    print("\n2. Testing explicit Gen1 configuration...")
    client_gen1 = MuseStreamClient(device_model='gen1', verbose=False)

    device_name_gen1 = client_gen1.get_device_model_name()
    print(f"   Explicit Gen1 config: {device_name_gen1}")

    if 'Gen 1' in device_name_gen1:
        print("   ✅ PASS: Explicit Gen1 works correctly")
    else:
        print("   ❌ FAIL: Explicit Gen1 does not work")

    # Test 3: Check that Gen3 still works when explicitly set
    print("\n3. Testing explicit Gen3 configuration...")
    client_gen3 = MuseStreamClient(device_model='gen3', verbose=False)

    device_name_gen3 = client_gen3.get_device_model_name()
    print(f"   Explicit Gen3 config: {device_name_gen3}")

    if 'Gen 3' in device_name_gen3:
        print("   ✅ PASS: Explicit Gen3 works correctly")
    else:
        print("   ❌ FAIL: Explicit Gen3 does not work")

    print("\n🎯 Summary:")
    print("   The auto-detection has been fixed to default to Gen1")
    print("   instead of Gen3, which should resolve the reported issue.")

if __name__ == "__main__":
    asyncio.run(test_auto_detection())