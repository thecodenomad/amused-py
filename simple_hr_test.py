#!/usr/bin/env python3
"""
Simple heart rate test with your Muse device
This will connect to your device and show real-time heart rate calculations
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from muse_decoder import MuseRealtimeDecoder
from muse_client import MuseStreamClient
import asyncio

def on_heart_rate(hr):
    """Handle heart rate data"""
    if hr:
        print(f"Heart Rate: {hr:.1f} BPM")

def on_ppg(data):
    """Handle PPG data"""
    # data is PPG dict with samples
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

    # Add samples to decoder's heart rate processor
    decoder.heart_rate_processor.add_ppg_samples(ppg_samples)

    print(f"Added {len(ppg_samples)} samples to PPG buffer")

    # Manually trigger heart rate calculation
    hr = decoder.heart_rate_processor.calculate_heart_rate()
    if hr:
        print(f"Calculated heart rate: {hr:.1f} BPM")
    else:
        print("Could not calculate heart rate (insufficient data or poor signal quality)")

    print(f"PPG buffer size after calculation: {len(decoder.heart_rate_processor.ppg_buffer)}")

    print("\nTest completed!")

    # Show final statistics
    stats = decoder.get_stats()
    print("\nFinal Statistics:")
    print(f"  Packets decoded: {stats['packets_decoded']}")
    print(f"  PPG samples collected: {stats['ppg_samples']}")
    if stats.get('last_heart_rate'):
        print(f"  Last heart rate: {stats['last_heart_rate']:.1f} BPM")
    if hr:
        print(f"  Final calculated heart rate: {hr:.1f} BPM")

async def test_with_device():
    """Test heart rate calculation with actual device"""

    print("=" * 60)
    print("Real-time Heart Rate Test with Your Muse Device")
    print("=" * 60)

    # Create client with auto device detection
    client = MuseStreamClient(device_model='auto', verbose=True)

    # Store all PPG samples for final calculation
    all_ppg_samples = []

    def collect_ppg_samples(data):
        """Collect PPG samples for final analysis"""
        if isinstance(data, dict) and 'samples' in data:
            samples = data['samples']
            all_ppg_samples.extend(samples)

    # Register callbacks using the new simplified API
    client.on_heart_rate(lambda hr: print(f"Heart Rate: {hr:.1f} BPM"))
    client.on_ppg(collect_ppg_samples)

    # Find device using built-in scanner
    print("Searching for Muse device...")
    device = await client.find_device()

    if not device:
        print("❌ No Muse device found!")
        print("Make sure your device is:")
        print("  - Turned on")
        print("  - In pairing mode")
        print("  - Bluetooth is enabled")
        return

    print(f"✅ Found device: {device.name} ({device.address})")

    print("\nStarting real-time streaming...")
    print("Compare these readings with your secondary device (60 BPM +/- 5 BPM)")
    print("Press Ctrl+C to stop\n")
    print("Expected: You should see PPG and EEG data being received...")

    try:
        success = await client.connect_and_stream(
            device.address,
            duration_seconds=30  # 30 second test
        )

        if success:
            print("\n✅ Test completed successfully!")
        else:
            print("\n❌ Connection failed")

    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")

    # Perform final heart rate calculation from all collected PPG samples
    final_hr = None
    if all_ppg_samples:
        print(f"\n🔄 Calculating final heart rate from {len(all_ppg_samples)} PPG samples...")

        # Create a temporary decoder for final calculation
        final_decoder = MuseRealtimeDecoder(device_model='gen1')

        final_decoder.heart_rate_processor.add_ppg_samples(all_ppg_samples)

        # Calculate final heart rate
        final_hr = final_decoder.heart_rate_processor.calculate_heart_rate()

        if final_hr:
            print(f"📊 Final calculated heart rate: {final_hr:.1f} BPM")
        else:
            print("📊 Could not calculate final heart rate")
    else:
        print("❌ No PPG samples collected!")

    # Show final statistics using the new client API
    stats = client.get_stats()
    print("\nFinal Statistics:")
    print(f"  Packets received: {stats['packets_received']}")
    print(f"  EEG samples: {stats.get('eeg_samples', 0)}")
    print(f"  PPG samples: {stats.get('ppg_samples', 0)}")
    print(f"  IMU samples: {stats.get('imu_samples', 0)}")
    if stats.get('last_heart_rate'):
        print(f"  Last real-time heart rate: {stats['last_heart_rate']:.1f} BPM")
    if final_hr:
        print(f"  Final calculated heart rate: {final_hr:.1f} BPM")

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