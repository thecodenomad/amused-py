#!/usr/bin/env python3
"""
Simple heart rate test with your Muse device
This will connect to your device and show real-time heart rate calculations
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from muse_realtime_decoder import MuseRealtimeDecoder
from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices
import asyncio

def on_heart_rate(data):
    """Handle heart rate data"""
    if data.heart_rate:
        print(".1f")

def on_ppg(data):
    """Handle PPG data"""
    # data is raw PPG dict, not DecodedData object
    if isinstance(data, dict) and 'samples' in data:
        print(f"[PPG] {len(data['samples'])} samples received")

async def test_with_device():
    """Test heart rate calculation with actual device"""

    print("=" * 60)
    print("Real-time Heart Rate Test with Your Muse Device")
    print("=" * 60)

    # Find device
    print("Searching for Muse device...")
    devices = await find_muse_devices(timeout=5.0)

    if not devices:
        print("❌ No Muse device found!")
        print("Make sure your device is:")
        print("  - Turned on")
        print("  - In pairing mode")
        print("  - Bluetooth is enabled")
        return

    device = devices[0]
    print(f"✅ Found device: {device.name} ({device.address})")

    # Create decoder and client
    decoder = MuseRealtimeDecoder(device_model='auto')

    # Register callbacks
    decoder.register_callback('heart_rate', on_heart_rate)
    decoder.register_callback('ppg', on_ppg)

    client = MuseStreamClient(
        save_raw=False,
        decode_realtime=True,
        verbose=False
    )

    # Set up client callbacks to use our decoder
    def handle_ppg(data):
        # data is raw PPG dict from MuseStreamClient
        if isinstance(data, dict) and 'samples' in data:
            # Add PPG samples to decoder buffer
            decoder.ppg_buffer.extend(data['samples'])
            # Try to calculate heart rate
            if len(decoder.ppg_buffer) > 32:
                # Create a dummy decoded data object for heart rate calculation
                from muse_realtime_decoder import DecodedData
                import datetime
                dummy_data = DecodedData(
                    timestamp=datetime.datetime.now(),
                    packet_type='PPG_TEST'
                )
                decoder._calculate_heart_rate(dummy_data)
                if len(decoder.ppg_buffer) > 320:
                    decoder.ppg_buffer = decoder.ppg_buffer[-320:]

    client.on_ppg(handle_ppg)

    print("\nStarting real-time streaming...")
    print("Compare these readings with your secondary device (64 BPM)")
    print("Press Ctrl+C to stop\n")

    try:
        success = await client.connect_and_stream(
            device.address,
            duration_seconds=60,  # 1 minute test
            preset='p1035'
        )

        if success:
            print("\n✅ Test completed successfully!")
        else:
            print("\n❌ Connection failed")

    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")

    # Show final statistics
    stats = decoder.get_stats()
    print("\nFinal Statistics:")
    print(f"  Packets decoded: {stats['packets_decoded']}")
    print(f"  PPG samples collected: {stats['ppg_samples']}")
    print(f"  Last heart rate: {stats['last_heart_rate']}")

if __name__ == "__main__":
    try:
        asyncio.run(test_with_device())
    except KeyboardInterrupt:
        print("\nStopped")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()