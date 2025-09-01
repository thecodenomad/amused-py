#!/usr/bin/env python3
"""
Gen3 Calibration Script for Muse S Heart Rate Monitoring

This script helps determine optimal calibration values for gen3 Muse S devices
by collecting PPG data and comparing against reference heart rate measurements.

Usage:
1. Connect your Muse S Gen3 device
2. Run this script: python gen3_calibration_script.py
3. Follow the prompts to collect data at different heart rates
4. The script will suggest optimal calibration values

Requirements:
- Muse S Gen3 device connected
- Reference heart rate monitor (watch, fitness tracker, etc.)
- scipy and numpy installed
"""

import asyncio
import time
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import json
import os
from datetime import datetime

from muse_stream_client import MuseStreamClient
from muse_discovery import find_muse_devices
from muse_realtime_decoder import MuseRealtimeDecoder, DecodedData


@dataclass
class CalibrationData:
    """Container for calibration data collected at a specific heart rate"""
    reference_hr: float  # Reference heart rate from external device
    muse_raw_hr: float   # Raw heart rate calculated by Muse
    ppg_samples: List[int]  # Raw PPG samples
    signal_quality: float  # Signal quality score
    timestamp: float


@dataclass
class CalibrationResult:
    """Results of calibration analysis"""
    scaling_factor: float
    baseline_offset: float
    quality_threshold: float
    mean_error: float
    std_error: float
    correlation: float


class Gen3Calibrator:
    """Handles calibration data collection and analysis for Gen3 devices"""

    def __init__(self):
        self.decoder = MuseRealtimeDecoder(device_model='gen3')
        self.calibration_data: List[CalibrationData] = []
        self.reference_rates = [60, 70, 80, 90, 100, 110]  # Target heart rates

    async def collect_calibration_data(self) -> List[CalibrationData]:
        """Collect calibration data at different heart rates"""
        print("🎯 Gen3 Calibration Data Collection")
        print("=" * 50)
        print("\nInstructions:")
        print("1. Have a reference heart rate monitor ready")
        print("2. We'll collect data at different heart rates")
        print("3. Follow prompts to change your activity level")
        print("4. Each collection period lasts 30 seconds")
        print("\nStarting in 5 seconds...")

        for i in range(5, 0, -1):
            print(f"\r{i}...", end="", flush=True)
            await asyncio.sleep(1)
        print("\rStarting calibration!\n")

        # Find Muse device
        devices = await find_muse_devices()
        if not devices:
            raise Exception("No Muse device found!")

        device = devices[0]
        print(f"📡 Connected to: {device.name}")

        # Create streaming client
        client = MuseStreamClient(
            device_model='gen3',
            save_raw=False,
            decode_realtime=True,
            verbose=False
        )

        collected_rates = []

        for target_hr in self.reference_rates:
            print(f"\n🎯 Target Heart Rate: {target_hr} BPM")
            print("   Adjust your activity to achieve this heart rate")
            print("   Press Enter when ready...")

            input()  # Wait for user

            print(f"📊 Collecting data for {target_hr} BPM (30 seconds)...")

            # Collect data for 30 seconds
            start_time = time.time()
            period_data = []

            def hr_callback(data: DecodedData):
                if data.heart_rate:
                    period_data.append({
                        'hr': data.heart_rate,
                        'timestamp': time.time()
                    })

            self.decoder.register_callback('heart_rate', hr_callback)

            # Stream for 30 seconds
            try:
                await client.connect_and_stream(
                    device.address,
                    duration_seconds=30,
                    preset='p1035'  # Full sensor mode
                )
            except Exception as e:
                print(f"Streaming error: {e}")
                continue

            # Calculate average heart rate for this period
            if period_data:
                avg_hr = np.mean([d['hr'] for d in period_data])
                print(".1f")
                collected_rates.append(avg_hr)

                # Ask for reference measurement
                print(f"   What does your reference device show? ", end="")
                try:
                    ref_hr = float(input())
                    print(".1f")
                    # Store calibration data point
                    self.calibration_data.append(CalibrationData(
                        reference_hr=ref_hr,
                        muse_raw_hr=avg_hr,
                        ppg_samples=[],  # Would need to collect PPG data separately
                        signal_quality=0.8,  # Placeholder
                        timestamp=time.time()
                    ))
                except ValueError:
                    print("   Invalid input, skipping this data point")
            else:
                print("   No heart rate data collected, skipping...")

        return self.calibration_data

    def analyze_calibration_data(self, data: List[CalibrationData]) -> CalibrationResult:
        """Analyze collected calibration data to find optimal parameters"""
        if len(data) < 3:
            raise ValueError("Need at least 3 data points for calibration")

        # Extract data
        ref_rates = np.array([d.reference_hr for d in data])
        muse_rates = np.array([d.muse_raw_hr for d in data])

        # Calculate linear regression: muse_rates = scaling_factor * ref_rates + baseline_offset
        # Rearranged: muse_rates - ref_rates = scaling_factor * ref_rates + baseline_offset - ref_rates
        # Let y = muse_rates, x = ref_rates
        # y = a*x + b, where a = scaling_factor, b = baseline_offset

        # Perform linear regression
        coeffs = np.polyfit(ref_rates, muse_rates, 1)
        scaling_factor = coeffs[0]
        baseline_offset = coeffs[1]

        # Calculate errors
        predicted_rates = scaling_factor * ref_rates + baseline_offset
        errors = muse_rates - predicted_rates
        mean_error = np.mean(errors)
        std_error = np.std(errors)

        # Calculate correlation
        correlation = np.corrcoef(ref_rates, muse_rates)[0, 1]

        # Suggest quality threshold (conservative approach)
        quality_threshold = 0.6  # Default value

        return CalibrationResult(
            scaling_factor=float(scaling_factor),
            baseline_offset=float(baseline_offset),
            quality_threshold=quality_threshold,
            mean_error=float(mean_error),
            std_error=float(std_error),
            correlation=float(correlation)
        )

    def generate_calibration_report(self, result: CalibrationResult) -> str:
        """Generate a human-readable calibration report"""
        report = f"""
🎯 Gen3 Calibration Results
{'='*40}

📊 Calibration Parameters:
   • Scaling Factor: {result.scaling_factor:.4f}
   • Baseline Offset: {result.baseline_offset:.2f} BPM
   • Quality Threshold: {result.quality_threshold:.2f}

📈 Accuracy Metrics:
   • Mean Error: {result.mean_error:.2f} BPM
   • Std Deviation: {result.std_error:.2f} BPM
   • Correlation: {result.correlation:.4f}

🔧 Recommended MuseRealtimeDecoder Configuration:

CALIBRATION_TABLES = {{
    'gen3_forehead': {{
        'ppg_scaling_factor': {result.scaling_factor:.4f},
        'ppg_baseline_offset': 0.0,
        'hr_scaling_factor': {result.scaling_factor:.4f},
        'hr_baseline_offset': {result.baseline_offset:.2f},
        'quality_threshold': {result.quality_threshold:.2f},
        'peak_prominence': 0.3,
        'ppg_range_min': 5000,
        'ppg_range_max': 30000
    }}
}}

{'✅ Good calibration!' if abs(result.correlation) > 0.8 else '⚠️  Calibration may need improvement'}
{'✅ Low error!' if abs(result.mean_error) < 5 else '⚠️  Consider recalibrating'}

💡 Tips for better calibration:
   • Collect data at more heart rate levels
   • Ensure good sensor contact during calibration
   • Use the same reference device consistently
   • Calibrate in the same environment as intended use
"""
        return report

    def save_calibration_data(self, data: List[CalibrationData], filename: str = None):
        """Save calibration data to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"gen3_calibration_{timestamp}.json"

        # Convert dataclasses to dictionaries
        data_dict = {
            'calibration_points': [
                {
                    'reference_hr': d.reference_hr,
                    'muse_raw_hr': d.muse_raw_hr,
                    'signal_quality': d.signal_quality,
                    'timestamp': d.timestamp
                }
                for d in data
            ],
            'collection_date': datetime.now().isoformat()
        }

        with open(filename, 'w') as f:
            json.dump(data_dict, f, indent=2)

        print(f"💾 Calibration data saved to: {filename}")


async def main():
    """Main calibration function"""
    print("🧠 Muse S Gen3 Heart Rate Calibration Tool")
    print("This tool will help you calibrate heart rate accuracy for your Gen3 device\n")

    calibrator = Gen3Calibrator()

    try:
        # Collect calibration data
        data = await calibrator.collect_calibration_data()

        if len(data) < 3:
            print("❌ Not enough data collected. Need at least 3 data points.")
            return

        # Analyze data
        result = calibrator.analyze_calibration_data(data)

        # Generate report
        report = calibrator.generate_calibration_report(result)
        print(report)

        # Save data
        calibrator.save_calibration_data(data)

        print("\n🎉 Calibration complete!")
        print("Update your MuseRealtimeDecoder with the recommended parameters.")

    except KeyboardInterrupt:
        print("\n⏹️  Calibration interrupted by user")
    except Exception as e:
        print(f"\n❌ Calibration error: {e}")
        print("Make sure your Muse device is connected and try again.")


if __name__ == "__main__":
    asyncio.run(main())