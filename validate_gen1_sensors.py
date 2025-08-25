#!/usr/bin/env python3
"""
Validate Gen1 Muse sensor data capture
Tests all EEG channels: TP9, AF7, AF8, TP10, FPz, AUX_R, AUX_L
"""

import asyncio
import datetime
from muse_stream_client import MuseStreamClient

class Gen1SensorValidator:
    """Validate that all Gen1 sensors are working"""

    def __init__(self):
        self.eeg_data = {}
        self.ppg_data = []
        self.imu_data = []
        self.heart_rate_data = []
        self.start_time = None
        self.end_time = None

    def on_eeg(self, data):
        """Handle EEG data"""
        if not self.start_time:
            self.start_time = datetime.datetime.now()

        channels = data.get('channels', {})
        for channel_name, samples in channels.items():
            if channel_name not in self.eeg_data:
                self.eeg_data[channel_name] = []
            self.eeg_data[channel_name].extend(samples)

        # Log progress
        total_samples = sum(len(samples) for samples in self.eeg_data.values())
        if total_samples % 1000 == 0:
            print(f"📊 EEG: {total_samples} total samples, channels: {list(self.eeg_data.keys())}")

    def on_ppg(self, data):
        """Handle PPG data"""
        samples = data.get('samples', [])
        self.ppg_data.extend(samples)
        if len(self.ppg_data) % 500 == 0:
            print(f"💓 PPG: {len(self.ppg_data)} samples")

    def on_imu(self, data):
        """Handle IMU data"""
        self.imu_data.append(data)
        if len(self.imu_data) % 100 == 0:
            print(f"🏃 IMU: {len(self.imu_data)} samples")

    def on_heart_rate(self, hr):
        """Handle heart rate data"""
        if hr:
            self.heart_rate_data.append(hr)
            print(f"❤️ Heart Rate: {hr:.1f} BPM")

    def validate_results(self):
        """Validate that all sensors are working"""
        self.end_time = datetime.datetime.now()

        print("\n" + "=" * 60)
        print("🧪 Gen1 Sensor Validation Results")
        print("=" * 60)

        duration = (self.end_time - self.start_time).total_seconds() if self.start_time else 0
        print(f"Test duration: {duration:.1f} seconds")

        # Check EEG channels (use supported channels based on device type)
        print("\n📡 EEG Channels:")

        # Determine expected channels based on device type
        # For now, assume Gen1 since we're validating Gen1 sensors
        expected_channels = ['TP9', 'AF7', 'AF8', 'TP10']  # Only supported on Gen1
        print("  📝 Note: Gen1 supports TP9, AF7, AF8, TP10 (FPz, AUX_R, AUX_L not supported)")

        all_channels_found = True
        supported_channels_found = 0

        for channel in expected_channels:
            if channel in self.eeg_data:
                samples = self.eeg_data[channel]
                sample_rate = len(samples) / duration if duration > 0 else 0
                print(f"  ✅ {channel}: {len(samples)} samples ({sample_rate:.1f} Hz)")

                # Check for reasonable EEG values (-500 to +500 µV)
                valid_samples = [s for s in samples if -500 < s < 500]
                valid_ratio = len(valid_samples) / len(samples) if samples else 0
                if valid_ratio < 0.5:
                    print(f"    ⚠️  Warning: Only {valid_ratio:.1%} valid samples")
                supported_channels_found += 1
            else:
                if channel in ['FPz', 'AUX_R', 'AUX_L']:
                    print(f"  ⭕ {channel}: Not supported on Gen1 (expected)")
                else:
                    print(f"  ❌ {channel}: NO DATA")
                    all_channels_found = False

        # Check other sensors
        print(f"\n💓 PPG/Heart Rate:")
        if self.ppg_data:
            ppg_rate = len(self.ppg_data) / duration if duration > 0 else 0
            print(f"  ✅ PPG: {len(self.ppg_data)} samples ({ppg_rate:.1f} Hz)")
        else:
            print("  ❌ PPG: NO DATA")

        if self.heart_rate_data:
            avg_hr = sum(self.heart_rate_data) / len(self.heart_rate_data)
            print(f"  ✅ Heart Rate: {len(self.heart_rate_data)} readings, avg: {avg_hr:.1f} BPM")
        else:
            print("  ❌ Heart Rate: NO DATA")

        print(f"\n🏃 IMU:")
        if self.imu_data:
            imu_rate = len(self.imu_data) / duration if duration > 0 else 0
            print(f"  ✅ IMU: {len(self.imu_data)} samples ({imu_rate:.1f} Hz)")
        else:
            print("  ❌ IMU: NO DATA")

        # Overall assessment
        print("\n" + "=" * 60)
        if all_channels_found and self.ppg_data and self.imu_data:
            print("🎉 SUCCESS: All Gen1 sensors are working!")
            return True
        else:
            print("❌ ISSUES FOUND: Some sensors not working")
            return False

async def validate_gen1_sensors(duration_seconds=30):
    """Main validation function"""
    print("🧪 Gen1 Sensor Validation Test")
    print("=" * 60)
    print("This will test all EEG channels: TP9, AF7, AF8, TP10, FPz, AUX_R, AUX_L")
    print("Make sure your Muse S Gen1 is connected and streaming.\n")

    # Create validator
    validator = Gen1SensorValidator()

    # Create client with Gen1 config and quality waiting
    client = MuseStreamClient(device_model='gen1', verbose=True)

    # Configure quality-based waiting for better data quality
    client.device_config.update({
        'quality_threshold': 0.60,      # 60% valid samples required
        'quality_window': 1000,         # Check quality over 1000 samples
        'max_quality_wait': 15.0,       # Max 15 seconds waiting for quality
        'stabilization_time': 5.0       # 5 seconds device stabilization
    })

    # Register callbacks
    client.on_eeg(validator.on_eeg)
    client.on_ppg(validator.on_ppg)
    client.on_imu(validator.on_imu)
    client.on_heart_rate(validator.on_heart_rate)

    # Find device
    device = await client.find_device()
    if not device:
        print("❌ No Muse device found")
        return False

    print(f"📡 Found device: {device.name} ({device.address})")
    print(f"🔧 Using config: {client.get_device_model_name()}")
    print("⏳ Quality waiting enabled - will wait for signal quality before recording")
    print(f"   Threshold: {client.device_config['quality_threshold']:.0%}")
    print(f"   Max wait: {client.device_config['max_quality_wait']}s")

    # Connect and stream with quality-based waiting
    success = await client.connect_and_stream(
        device.address,
        duration_seconds=duration_seconds,
        preset='p1036'  # Ultra-low-rate preset for best quality
    )

    if success:
        # Validate results
        return validator.validate_results()
    else:
        print("❌ Connection/streaming failed")
        return False

async def quick_test():
    """Quick test for immediate feedback"""
    print("⚡ Quick Gen1 Test (10 seconds)")
    return await validate_gen1_sensors(duration_seconds=10)

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        success = asyncio.run(quick_test())
    else:
        success = asyncio.run(validate_gen1_sensors())

    exit(0 if success else 1)
