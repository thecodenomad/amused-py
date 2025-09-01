#!/usr/bin/env python3
"""
Example of the cleaned up Muse API
Demonstrates the simplified interface and modular design
"""

import asyncio
from muse_client import MuseStreamClient, stream_device


async def simple_example():
    """Simple streaming example with callbacks"""
    print("=== Clean Muse API Example ===\n")

    # Create client with auto-detection
    client = MuseStreamClient(device_model='auto', verbose=True)

    # Register simple callbacks
    client.on_eeg(lambda data: print(f"EEG: {len(data['channels'])} channels"))
    client.on_heart_rate(lambda hr: print(f"Heart Rate: {hr:.1f} BPM"))

    # Find and connect
    device = await client.find_device()
    if device:
        print(f"Found device: {device.name}")
        success = await client.connect_and_stream(device.address, duration_seconds=10)

        if success:
            stats = client.get_stats()
            print("\nSession Summary:")
            print(f"  Packets received: {stats['packets_received']}")
            print(f"  EEG samples: {stats['eeg_samples']}")
            print(f"  PPG samples: {stats['ppg_samples']}")
            if stats.get('last_heart_rate'):
                print(f"  Last heart rate: {stats['last_heart_rate']:.1f} BPM")


async def convenience_function_example():
    """Example using the convenience function"""
    print("\n=== Convenience Function Example ===\n")

    # Stream for 15 seconds with auto-detection
    stats = await stream_device(duration_seconds=15, device_model='auto')

    if stats:
        print("Streaming completed successfully!")
    else:
        print("Streaming failed or no device found")


def main():
    """Main function"""
    print("Muse API Cleanup Demonstration")
    print("==============================")

    try:
        # Run examples
        asyncio.run(simple_example())
        asyncio.run(convenience_function_example())

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()