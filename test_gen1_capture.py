#!/usr/bin/env python3
"""
Test script to capture raw data from Muse S Gen 1
This will help identify protocol differences from Gen 3 (Athena)
"""

import asyncio
import datetime
from typing import List, Optional
from dataclasses import dataclass
from bleak import BleakClient, BleakScanner
import os

@dataclass
class RawPacket:
    """Raw packet capture"""
    timestamp: datetime.datetime
    data: bytes
    packet_num: int

class Gen1DataCapture:
    """Capture raw packets from Muse S Gen 1"""

    def __init__(self):
        self.packets: List[RawPacket] = []
        self.packet_count = 0
        self.capture_file = f"muse_gen1_capture_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"

    async def find_muse_device(self) -> Optional[str]:
        """Find Muse device"""
        print("🔍 Scanning for Muse devices...")
        devices = await BleakScanner.discover(timeout=5.0)

        for device in devices:
            if device.name and "Muse" in device.name:
                print(f"📡 Found: {device.name} ({device.address})")
                return device.address

        print("❌ No Muse device found")
        return None

    def handle_sensor_notification(self, sender, data: bytearray):
        """Capture raw sensor data"""
        timestamp = datetime.datetime.now()
        self.packet_count += 1

        packet = RawPacket(
            timestamp=timestamp,
            data=bytes(data),
            packet_num=self.packet_count
        )
        self.packets.append(packet)

        # Log first few packets in detail
        if self.packet_count <= 5:
            print(f"📦 Packet {self.packet_count}: {data.hex()[:50]}... (len={len(data)})")

        # Periodic status
        if self.packet_count % 50 == 0:
            print(f"📊 Captured {self.packet_count} packets")

    async def capture_packets(self, address: str, duration_seconds: int = 30) -> bool:
        """Capture raw packets from device"""
        print(f"🎯 Connecting to {address}...")

        try:
            async with BleakClient(address) as client:
                print("✅ Connected!")

                # Enable sensor notifications
                sensor_uuids = [
                    "273e0013-4c4d-454d-96be-f03bac821358",  # Combined sensors
                    "273e0003-4c4d-454d-96be-f03bac821358",  # EEG TP9
                ]

                sensor_enabled = False
                for uuid in sensor_uuids:
                    try:
                        await client.start_notify(uuid, self.handle_sensor_notification)
                        print(f"📡 Sensor notifications enabled ({uuid})")
                        sensor_enabled = True
                        break
                    except Exception as e:
                        print(f"⚠️ Failed to enable {uuid}: {e}")
                        continue

                if not sensor_enabled:
                    print("❌ Failed to enable sensor notifications")
                    return False

                # Send basic commands to start streaming
                control_uuid = "273e0001-4c4d-454d-96be-f03bac821358"

                # Try different command sequences for Gen 1
                commands_to_try = [
                    ("Version", bytes.fromhex('0376360a')),
                    ("Status", bytes.fromhex('02730a')),
                    ("Halt", bytes.fromhex('02680a')),
                    ("Preset p21", bytes.fromhex('047032310a')),
                    ("Stream start", bytes.fromhex('0664633030310a')),  # dc001
                ]

                for cmd_name, cmd_bytes in commands_to_try:
                    try:
                        await client.write_gatt_char(control_uuid, cmd_bytes, response=False)
                        print(f"📤 Sent {cmd_name}: {cmd_bytes.hex()}")
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        print(f"⚠️ Failed to send {cmd_name}: {e}")

                # Wait for streaming to start
                print(f"⏳ Capturing for {duration_seconds} seconds...")
                await asyncio.sleep(duration_seconds)

                return True

        except Exception as e:
            print(f"❌ Error: {e}")
            return False

    def save_capture(self):
        """Save captured packets to file"""
        if not self.packets:
            print("⚠️ No packets to save")
            return

        print(f"💾 Saving {len(self.packets)} packets to {self.capture_file}")

        with open(self.capture_file, 'wb') as f:
            # Write header
            header = f"MUSE_GEN1_CAPTURE\n{len(self.packets)}\n".encode()
            f.write(header)

            # Write packets
            for packet in self.packets:
                # Write timestamp and data length
                timestamp_bytes = str(packet.timestamp.timestamp()).encode()[:8].ljust(8, b'\x00')
                length_bytes = len(packet.data).to_bytes(4, 'little')

                f.write(timestamp_bytes)
                f.write(length_bytes)
                f.write(packet.data)

        print(f"✅ Saved to {self.capture_file}")

    def analyze_packets(self):
        """Analyze captured packets"""
        if not self.packets:
            print("⚠️ No packets to analyze")
            return

        print("\n📊 Packet Analysis:")
        print(f"Total packets: {len(self.packets)}")

        # Analyze packet lengths
        lengths = [len(p.data) for p in self.packets]
        print(f"Packet lengths: {set(lengths)}")

        # Analyze first bytes (packet types)
        first_bytes = [p.data[0] if len(p.data) > 0 else 0 for p in self.packets]
        unique_types = set(first_bytes)
        print(f"Packet types (first byte): {[f'0x{b:02x}' for b in sorted(unique_types)]}")

        # Show distribution
        type_counts = {}
        for b in first_bytes:
            type_counts[b] = type_counts.get(b, 0) + 1

        print("Type distribution:")
        for b in sorted(type_counts.keys()):
            count = type_counts[b]
            pct = count / len(self.packets) * 100
            print(f"  0x{b:02x}: {count} packets ({pct:.1f}%)")

        # Show sample packets
        print("\n📋 Sample packets:")
        for i, packet in enumerate(self.packets[:3]):
            print(f"  Packet {i+1}: {packet.data.hex()[:60]}...")

async def main():
    """Main test function"""
    print("🧪 Muse S Gen 1 Data Capture Test")
    print("=" * 50)

    capture = Gen1DataCapture()

    # Find device
    address = await capture.find_muse_device()
    if not address:
        return

    # Capture data
    success = await capture.capture_packets(address, duration_seconds=30)

    if success:
        # Analyze results
        capture.analyze_packets()

        # Save for later analysis
        capture.save_capture()

        print("\n✅ Test complete!")
        print(f"Captured {len(capture.packets)} packets")
        print(f"Data saved to: {capture.capture_file}")

if __name__ == "__main__":
    asyncio.run(main())