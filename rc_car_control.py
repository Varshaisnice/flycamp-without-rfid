#!/usr/bin/env python3
"""
send_tty_on_game_start.py

Sends ASCII '2' to /dev/ttyACM1 when the "game is started" (i.e., when this script runs),
then waits 15 seconds and sends ASCII '0'.

Usage:
  - Make executable: chmod +x send_tty_on_game_start.py
  - Run: ./send_tty_on_game_start.py

Notes:
  - This script first attempts to use pyserial (recommended). If pyserial is not installed,
    it falls back to opening the device file directly.
  - You may need appropriate permissions to write to /dev/ttyACM1 (run with sudo or add your user
    to the dialout/tty group as appropriate).
  - If your device node is different, change DEVICE below.
"""

import os
import sys
import time

DEVICE = "/dev/ttyACM0"
BAUDRATE = 9600  # only used if pyserial is available; harmless otherwise
SEND_FIRST = b'2'  # ASCII 2
SEND_SECOND = b'0'  # ASCII 0
DELAY_SECONDS = 30


def write_direct(device_path: str, data: bytes) -> None:
    """
    Write bytes directly to device file.
    """
    with open(device_path, "wb", buffering=0) as f:
        f.write(data)


def write_serial(device_path: str, data: bytes, baudrate: int = 921600) -> None:
    """
    Write bytes using pyserial.Serial for more robust serial setup.
    """
    import serial
    with serial.Serial(device_path, baudrate=baudrate, timeout=1) as ser:
        ser.write(data)
        ser.flush()


def send_byte(device: str, data: bytes) -> None:
    """
    Try to send data using pyserial if available; otherwise fall back to direct write.
    """
    try:
        # Try to import serial (pyserial)
        write_serial(device, data, BAUDRATE)
        print(f"Sent {data!r} to {device} via pyserial.")
    except Exception as e:
        # If anything goes wrong (module not installed or serial open error),
        # attempt direct write and surface a helpful message.
        try:
            write_direct(device, data)
            print(f"Sent {data!r} to {device} via direct device write.")
        except Exception as e2:
            print(f"Failed to write to {device}: {e2}", file=sys.stderr)
            raise


def ensure_device_exists(device_path: str) -> None:
    if not os.path.exists(device_path):
        raise FileNotFoundError(f"Device {device_path} does not exist. Check the path.")


def main():
    try:
        ensure_device_exists(DEVICE)
    except FileNotFoundError as fe:
        print(str(fe), file=sys.stderr)
        sys.exit(2)

    try:
        # "Game started" — send ASCII '2'
        send_byte(DEVICE, SEND_FIRST)

        # Wait for 15 seconds (while the game is running)
        time.sleep(DELAY_SECONDS)

        # Send ASCII '0'
        send_byte(DEVICE, SEND_SECOND)
    except Exception as exc:
        print(f"Error during send sequence: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
