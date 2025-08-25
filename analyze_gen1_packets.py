#!/usr/bin/env python3
"""
Analyze Gen1 packet structure to understand EEG channel organization
"""

import json
import struct
from typing import List, Dict, Any

def analyze_eeg_packet(hex_data: str):
    """Analyze a single EEG packet"""
    data = bytes.fromhex(hex_data)
    print(f"Packet size: {len(data)} bytes")
    print(f"First byte: 0x{data[0]:02x}")

    # Skip header (first 4 bytes)
    offset = 4
    print(f"Header: {data[:4].hex()}")

    # Look for EEG segments (18 bytes each)
    eeg_segments = []
    while offset + 18 <= len(data):
        segment = data[offset:offset+18]
        eeg_segments.append(segment)
        offset += 18

    print(f"Found {len(eeg_segments)} potential EEG segments")

    # Analyze each segment
    for i, segment in enumerate(eeg_segments):
        print(f"\nSegment {i}: {segment.hex()}")

        # Extract samples (12-bit values packed in 18 bytes)
        samples = []
        for j in range(6):  # 6 groups of 3 bytes = 12 samples
            group_offset = j * 3
            if group_offset + 3 <= len(segment):
                b0, b1, b2 = segment[group_offset:group_offset+3]
                sample1 = (b0 << 4) | (b1 >> 4)
                sample2 = ((b1 & 0x0F) << 8) | b2
                samples.extend([sample1, sample2])

        print(f"  Raw samples: {samples}")

        # Convert to microvolts
        scale = 1000.0 / 2048.0
        uv_samples = [(s - 2048) * scale for s in samples]
        print(f"  Microvolts: {[f'{uv:.1f}' for uv in uv_samples[:4]]}...")

        # Check if values are in reasonable EEG range
        valid_samples = [uv for uv in uv_samples if -500 < uv < 500]
        print(f"  Valid samples: {len(valid_samples)}/{len(uv_samples)}")

def analyze_imu_packet(hex_data: str):
    """Analyze a single IMU packet"""
    data = bytes.fromhex(hex_data)
    print(f"Packet size: {len(data)} bytes")
    print(f"First byte: 0x{data[0]:02x}")

    # Skip header (first 4 bytes)
    offset = 4
    print(f"Header: {data[:4].hex()}")

    # Look for IMU data (16 bytes per sample)
    imu_segments = []
    while offset + 16 <= len(data):
        segment = data[offset:offset+16]
        imu_segments.append(segment)
        offset += 16

    print(f"Found {len(imu_segments)} potential IMU segments")

    # Analyze first segment
    if imu_segments:
        segment = imu_segments[0]
        print(f"\nFirst IMU segment: {segment.hex()}")

        try:
            # Extract accelerometer and gyroscope (16-bit signed values)
            ax = struct.unpack('>h', segment[0:2])[0]
            ay = struct.unpack('>h', segment[2:4])[0]
            az = struct.unpack('>h', segment[4:6])[0]
            gx = struct.unpack('>h', segment[6:8])[0]
            gy = struct.unpack('>h', segment[8:10])[0]
            gz = struct.unpack('>h', segment[10:12])[0]

            print(f"  Accel: x={ax}, y={ay}, z={az}")
            print(f"  Gyro:  x={gx}, y={gy}, z={gz}")
        except Exception as e:
            print(f"  Error parsing IMU: {e}")

def main():
    """Main analysis function"""
    # Load test data
    with open('/var/home/codenomad/Development/amused-py/tests/test_data/muse_20250824_172756_samples.json', 'r') as f:
        data = json.load(f)

    print("=== Analyzing EEG Packets ===")
    for i, packet in enumerate(data['eeg_packets'][:2]):  # First 2 packets
        print(f"\n{'='*50}")
        print(f"EEG PACKET {i+1}")
        print('='*50)
        analyze_eeg_packet(packet['hex'])

    print("\n\n=== Analyzing IMU Packets ===")
    for i, packet in enumerate(data['imu_packets'][:2]):  # First 2 packets
        print(f"\n{'='*50}")
        print(f"IMU PACKET {i+1}")
        print('='*50)
        analyze_imu_packet(packet['hex'])

if __name__ == "__main__":
    main()