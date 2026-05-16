#!/usr/bin/env python3
"""
Run this script on YOUR LOCAL MACHINE (not in the cloud).
It bridges the micro:bit serial port to a WebSocket server.

Requirements: pip install pyserial websockets
Then expose it: ngrok http 5678
"""

import asyncio
import serial
import serial.tools.list_ports
import sys
import websockets

PORT = 5678


def find_microbit():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = (p.description or "").lower()
        manufacturer = (p.manufacturer or "").lower()
        if p.vid == 0x0D28 or "micro:bit" in desc or "mbed" in desc or "microbit" in manufacturer:
            return p.device
    if ports:
        print("micro:bit not detected by name, available ports:")
        for i, p in enumerate(ports):
            print(f"  [{i}] {p.device} — {p.description}")
        choice = input("Enter number to use: ").strip()
        return ports[int(choice)].device
    return None


async def bridge(websocket, ser):
    async def serial_to_ws():
        loop = asyncio.get_event_loop()
        try:
            while True:
                data = await loop.run_in_executor(None, ser.read, 256)
                if data:
                    await websocket.send(data)
        except websockets.ConnectionClosed:
            pass

    async def ws_to_serial():
        try:
            async for message in websocket:
                if isinstance(message, str):
                    message = message.encode()
                ser.write(message)
        except websockets.ConnectionClosed:
            pass

    await asyncio.gather(serial_to_ws(), ws_to_serial())


async def main():
    port = find_microbit()
    if not port:
        print("No serial ports found. Is the micro:bit plugged in?")
        sys.exit(1)

    baud = 115200
    print(f"Opening micro:bit on {port} at {baud} baud...")
    try:
        ser = serial.Serial(port, baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"Failed to open port: {e}")
        sys.exit(1)

    async def handler(websocket):
        print(f"Cloud connected from {websocket.remote_address}")
        try:
            await bridge(websocket, ser)
        finally:
            print("Client disconnected, waiting for next connection...")

    print(f"\nWebSocket bridge ready on port {PORT}")
    print("─" * 40)
    print("Now run in another terminal:")
    print("  ngrok http 5678")
    print("─" * 40)
    print("Then give Claude the ngrok https URL (e.g. https://abc123.ngrok-free.app)\n")

    async with websockets.serve(handler, "0.0.0.0", PORT):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down.")
