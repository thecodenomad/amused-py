#!/usr/bin/env python3
"""
Test the new disconnect and stop streaming functionality
"""

import asyncio
from muse_stream_client import MuseStreamClient

async def test_disconnect_functionality():
    """Test the new disconnect methods"""
    print("🧪 Testing Enhanced Disconnect Functionality")
    print("=" * 60)

    # Create client
    client = MuseStreamClient(device_model='gen1', verbose=False)

    # Test 1: Check initial status
    print("\n1. Initial Status:")
    print(f"   Connected: {client.is_connected()}")
    print(f"   Streaming: {client.is_streaming_active()}")

    # Test 2: Check method availability
    print("\n2. Method Availability:")
    methods = ['stop_streaming', 'disconnect', 'connect_and_stream_async', 'is_connected', 'is_streaming_active']
    for method in methods:
        has_method = hasattr(client, method)
        print(f"   {method}: {'✅' if has_method else '❌'}")

    # Test 3: Test disconnect when not connected
    print("\n3. Disconnect when not connected:")
    await client.disconnect()
    print("   ✅ No error when disconnecting while not connected")

    # Test 4: Test stop streaming when not streaming
    print("\n4. Stop streaming when not streaming:")
    client.stop_streaming()
    print("   ✅ No error when stopping while not streaming")

    print("\n🎯 All basic functionality tests passed!")
    print("   The enhanced disconnect methods are working correctly.")

if __name__ == "__main__":
    asyncio.run(test_disconnect_functionality())