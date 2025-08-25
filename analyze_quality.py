#!/usr/bin/env python3
"""
Analyze Gen1 data quality to determine if we can improve beyond 46% valid samples
"""

import asyncio
import datetime
from muse_stream_client import MuseStreamClient

async def analyze_data_quality():
    """Analyze current Gen1 data quality metrics"""
    print("🔬 Analyzing Gen1 Data Quality")
    print("=" * 50)

    # Data collection
    eeg_data = {'TP9': [], 'AF7': [], 'AF8': [], 'TP10': []}
    ppg_data = []
    imu_data = []
    start_time = None

    def on_eeg(data):
        nonlocal start_time
        if not start_time:
            start_time = datetime.datetime.now()

        channels = data.get('channels', {})
        for channel_name, samples in channels.items():
            if channel_name in eeg_data:
                eeg_data[channel_name].extend(samples)

    def on_ppg(data):
        samples = data.get('samples', [])
        ppg_data.extend(samples)

    def on_imu(data):
        imu_data.append(data)

    # Test with current settings
    client = MuseStreamClient(device_model='gen1', verbose=False)

    # Configure quality-based waiting
    client.device_config.update({
        'quality_threshold': 0.6,
        'quality_window': 1000,
        'max_quality_wait': 15.0,
        'stabilization_time': 5.0
    })

    # Register callbacks
    client.on_eeg(on_eeg)
    client.on_ppg(on_ppg)
    client.on_imu(on_imu)

    # Find device
    device = await client.find_device()
    if not device:
        print("❌ No Muse device found")
        return

    print(f"📡 Found device: {device.name}")

    # Connect and stream for 20 seconds
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=20,
        preset='p1036'  # Current preset
    )

    if not success:
        print("❌ Connection/streaming failed")
        return

    # Analyze results
    end_time = datetime.datetime.now()
    total_duration = (end_time - start_time).total_seconds() if start_time else 0

    print("\n📊 Quality Analysis Results:")
    print(f"   Duration: {total_duration:.1f}s")
    print(f"   PPG Samples: {len(ppg_data)}")
    print(f"   IMU Samples: {len(imu_data)}")

    # Analyze EEG quality
    total_samples = 0
    valid_samples = 0
    channel_stats = {}

    print("\n🧠 EEG Channel Analysis:")
    for channel_name, samples in eeg_data.items():
        total_samples += len(samples)
        # Check for reasonable EEG values (-500 to +500 µV)
        valid = [s for s in samples if -500 < s < 500]
        valid_samples += len(valid)
        valid_ratio = len(valid) / len(samples) if samples else 0

        channel_stats[channel_name] = {
            'samples': len(samples),
            'valid_ratio': valid_ratio,
            'rate': len(samples) / total_duration if total_duration > 0 else 0
        }

        print(f"   {channel_name}: {len(samples)} samples, {valid_ratio:.1%} valid")

    overall_valid_ratio = valid_samples / total_samples if total_samples > 0 else 0

    print("\n📈 Overall Results:")
    print(f"   Total EEG Samples: {total_samples}")
    print(f"   Valid EEG Samples: {valid_samples}")
    print(f"   Valid Ratio: {overall_valid_ratio:.1%}")
    print(f"   Sample Rate: {total_samples/total_duration:.1f} Hz" if total_duration > 0 else "   Sample Rate: N/A")

    # Assessment
    print("\n🔍 Assessment:")
    if overall_valid_ratio > 0.8:
        print("   ✅ Excellent quality (>80% valid)")
    elif overall_valid_ratio > 0.6:
        print("   🟡 Good quality (60-80% valid)")
    elif overall_valid_ratio > 0.4:
        print("   🟠 Moderate quality (40-60% valid)")
    else:
        print("   ❌ Poor quality (<40% valid)")

    # Recommendations
    print("\n💡 Recommendations:")
    if overall_valid_ratio < 0.6:
        print("   • Try different preset (p21, p22, p23)")
        print("   • Adjust quality threshold (lower to 0.3-0.5)")
        print("   • Increase stabilization time (10-15s)")
        print("   • Check electrode contact quality")
    else:
        print("   • Current settings are working well")
        print("   • Consider fine-tuning for even better quality")

    return overall_valid_ratio

if __name__ == "__main__":
    result = asyncio.run(analyze_data_quality())
    if result is not None:
        print(f"\n🎯 Current valid sample ratio: {result:.1%}")
        if result < 0.6:
            print("🔄 Consider running optimization test to find better settings")
        else:
            print("✅ Quality is acceptable for most applications")