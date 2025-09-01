#!/usr/bin/env python3
"""
Quick test to check Gen1 data quality with minimal output
"""

import asyncio
import datetime
from muse_stream_client import MuseStreamClient

async def quick_quality_test():
    """Quick test of current Gen1 quality"""
    print("🔬 Quick Gen1 Quality Test")
    print("=" * 40)

    # Create client with Gen1 config
    client = MuseStreamClient(device_model='gen1', verbose=False)

    # Configure quality-based waiting
    client.device_config.update({
        'quality_threshold': 0.6,
        'quality_window': 1000,
        'max_quality_wait': 15.0,
        'stabilization_time': 5.0
    })

    # Find device
    device = await client.find_device()
    if not device:
        print("❌ No Muse device found")
        return

    print(f"📡 Found device: {device.name}")

    # Simple data collector
    eeg_data = {}
    start_time = None

    def on_eeg(data):
        nonlocal start_time
        if not start_time:
            start_time = datetime.datetime.now()

        channels = data.get('channels', {})
        for channel_name, samples in channels.items():
            if channel_name not in eeg_data:
                eeg_data[channel_name] = []
            eeg_data[channel_name].extend(samples)

    client.on_eeg(on_eeg)

    # Connect and stream for 10 seconds
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=10,
        preset='p1036'
    )

    if not success:
        print("❌ Connection/streaming failed")
        return

    # Calculate quality
    end_time = datetime.datetime.now()
    total_duration = (end_time - start_time).total_seconds() if start_time else 0

    total_samples = 0
    valid_samples = 0

    for channel_name, samples in eeg_data.items():
        total_samples += len(samples)
        valid = [s for s in samples if -500 < s < 500]
        valid_samples += len(valid)

    valid_ratio = valid_samples / total_samples if total_samples > 0 else 0

    print("\n📊 Results:")
    print(f"   Duration: {total_duration:.1f}s")
    print(f"   Total Samples: {total_samples}")
    print(f"   Valid Samples: {valid_samples}")
    print(f"   Valid Ratio: {valid_ratio:.1%}")
    print(f"   Sample Rate: {total_samples/total_duration:.1f} Hz" if total_duration > 0 else "   Sample Rate: N/A")

    if valid_ratio > 0.5:
        print("   ✅ Good quality data")
    else:
        print("   ⚠️  Low quality data")

if __name__ == "__main__":
    asyncio.run(quick_quality_test())