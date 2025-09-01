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

def test_decoder_only():
    """Test MuseRealtimeDecoder with synthetic data"""
    print("=" * 60)
    print("MuseRealtimeDecoder Test with Synthetic Data")
    print("=" * 60)

    # Create decoder
    decoder = MuseRealtimeDecoder(device_model='gen1')

    # Register callback
    def on_hr(hr):
        if hr:
            print(f"Heart Rate: {hr:.1f} BPM")

    decoder.register_callback('heart_rate', on_hr)

    # Generate synthetic PPG data (simulating ~75 BPM) with correct sampling
    import numpy as np
    sample_rate = 64  # Muse typical sampling rate
    duration = 10  # 10 seconds
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Create PPG signal with heart rate around 75 BPM
    heart_rate_freq = 1.25  # 75 BPM = 1.25 Hz
    # PPG signals typically have baseline around 1000-2000 with amplitude 50-200
    ppg_signal = 1500 + 100 * np.sin(2 * np.pi * heart_rate_freq * t)

    # Add realistic noise (PPG signals have varying noise levels)
    noise = np.random.normal(0, 20, len(ppg_signal))
    ppg_signal += noise

    # Add some baseline wander (common in PPG)
    baseline_wander = 50 * np.sin(2 * np.pi * 0.1 * t)  # 0.1 Hz slow variation
    ppg_signal += baseline_wander

    # Ensure values are in realistic PPG range
    ppg_signal = np.clip(ppg_signal, 800, 3000)

    # Convert to integers (simulating real Muse data)
    ppg_samples = [int(x) for x in ppg_signal]

    print(f"Generated {len(ppg_samples)} synthetic PPG samples")
    print("Expected heart rate: ~75 BPM")

    # Directly add samples to decoder buffer (bypass packet decoding for testing)
    decoder.ppg_buffer.extend(ppg_samples)

    print(f"Added {len(ppg_samples)} samples to PPG buffer")

    # Force sampling rate detection to use correct rate
    decoder.stable_sampling_rate = 64.0
    decoder.sampling_rate_confidence = 10

    # Manually trigger heart rate calculation
    from muse_realtime_decoder import DecodedData
    import datetime
    dummy_data = DecodedData(timestamp=datetime.datetime.now(), packet_type='TEST')

    # Force heart rate calculation
    decoder._calculate_heart_rate(dummy_data)

    print(f"PPG buffer size after calculation: {len(decoder.ppg_buffer)}")

    print("\nTest completed!")

    # Show final statistics
    stats = decoder.get_stats()
    print("\nFinal Statistics:")
    print(f"  Packets decoded: {stats['packets_decoded']}")
    print(f"  PPG samples collected: {stats['ppg_samples']}")
    print(f"  Last heart rate: {stats['last_heart_rate']}")

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
    decoder.register_callback('heart_rate', lambda data: print(f"Heart Rate: {data.heart_rate:.1f} BPM") if data.heart_rate else None)
    decoder.register_callback('ppg', lambda data: print(f"[PPG] {len(data.ppg.get('samples', [])) if data.ppg else 0} samples received"))

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
            if len(decoder.ppg_buffer) > 64:
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
    print("Compare these readings with your secondary device (60 BPM +/- 5 BPM)")
    print("Press Ctrl+C to stop\n")

    try:
        success = await client.connect_and_stream(
            device.address,
            duration_seconds=30,  # 30 second test
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
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        test_decoder_only()
    else:
        try:
            asyncio.run(test_with_device())
        except KeyboardInterrupt:
            print("\nStopped")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()