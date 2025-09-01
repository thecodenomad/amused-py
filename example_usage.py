#!/usr/bin/env python3
"""
Example usage of the Amused package
Demonstrates how to use the package after installation
"""

from amused import MuseStreamClient, get_device_config, MuseRealtimeDecoder

def main():
    print("🎯 Amused Package Usage Example")
    print("=" * 40)

    # 1. Create a streaming client
    print("\n1. Creating Muse Stream Client...")
    client = MuseStreamClient(device_model='auto', verbose=True)
    print("✅ Client created successfully!")

    # 2. Get device configuration
    print("\n2. Getting device configuration...")
    gen1_config = get_device_config('gen1')
    gen3_config = get_device_config('gen3')
    print(f"✅ Gen1: {gen1_config['name']} ({gen1_config['eeg_channels']} channels)")
    print(f"✅ Gen3: {gen3_config['name']} ({gen3_config['eeg_channels']} channels)")

    # 3. Create a decoder
    print("\n3. Creating real-time decoder...")
    decoder = MuseRealtimeDecoder(device_model='gen1')
    print("✅ Decoder created successfully!")

    # 4. Register callbacks (example)
    print("\n4. Setting up callbacks...")

    def on_eeg(data):
        print(f"📊 EEG data received: {len(data.get('channels', {}))} channels")

    def on_heart_rate(hr):
        print(f"💓 Heart rate: {hr:.1f} BPM")

    client.on_eeg(on_eeg)
    client.on_heart_rate(on_heart_rate)
    print("✅ Callbacks registered!")

    print("\n🎉 Package is ready for use!")
    print("\nTo start streaming:")
    print("  # Find and connect to a Muse device")
    print("  # device = await client.find_device()")
    print("  # await client.connect_and_stream(device.address, duration_seconds=30)")

if __name__ == "__main__":
    main()