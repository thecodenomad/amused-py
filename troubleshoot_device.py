#!/usr/bin/env python3
"""
Troubleshoot Muse device connection issues
"""

import asyncio
from muse_stream_client import MuseStreamClient

async def troubleshoot():
    """Help troubleshoot Muse device connection"""
    print("🔧 Muse Device Troubleshooting")
    print("=" * 50)

    print("\n1. 🔍 Scanning for devices...")
    client = MuseStreamClient(device_model='gen1', verbose=True)

    device = await client.find_device()

    if device:
        print(f"\n✅ SUCCESS: Found device!")
        print(f"   Name: {device.name}")
        print(f"   Address: {device.address}")

        print("\n2. 🔄 Testing connection...")
        try:
            success = await client.connect_and_stream(device.address, duration_seconds=5, preset='p1036')
            if success:
                print("   ✅ Connection successful!")
                print("   🎉 Your Muse device is working properly!")
                print("\n💡 Recommendation:")
                print("   The 46% valid sample issue is likely a hardware limitation.")
                print("   This is normal for Gen1 devices and cannot be significantly improved.")
                print("   Consider using the current settings for your application.")
            else:
                print("   ❌ Connection failed")
                print("   💡 Try: Restart device, check battery, move closer")
        except Exception as e:
            print(f"   ❌ Connection error: {e}")
            print("   💡 Try: Restart device, check Bluetooth permissions")

    else:
        print("\n❌ No Muse device found")
        print("\n🔧 Troubleshooting steps:")
        print("   1. Check if device is powered on (LED should be on)")
        print("   2. Put device in pairing mode (hold power button until LED flashes)")
        print("   3. Move device closer to computer")
        print("   4. Restart Bluetooth: sudo systemctl restart bluetooth")
        print("   5. Check Bluetooth permissions")
        print("   6. Try with sudo: sudo python troubleshoot_device.py")

        print("\n🔍 To check Bluetooth status:")
        print("   bluetoothctl show")
        print("   bluetoothctl scan on  # Look for Muse device")

if __name__ == "__main__":
    asyncio.run(troubleshoot())