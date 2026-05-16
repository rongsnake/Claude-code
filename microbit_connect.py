#!/usr/bin/env python3
"""
Connects to a micro:bit via the local WebSocket bridge (through ngrok https).
Usage: python microbit_connect.py <wss-url>
       python microbit_connect.py wss://abc123.ngrok-free.app
"""

import asyncio
import sys
import websockets


async def repl(url):
    if url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://"):]

    print(f"Connecting to {url}...")
    async with websockets.connect(url) as ws:
        print("Connected to micro:bit.\n")

        async def receive():
            try:
                async for message in ws:
                    if isinstance(message, bytes):
                        sys.stdout.write(message.decode(errors="replace"))
                    else:
                        sys.stdout.write(message)
                    sys.stdout.flush()
            except websockets.ConnectionClosed:
                print("\n[connection closed]")

        async def send():
            loop = asyncio.get_event_loop()
            while True:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                await ws.send(line.encode())

        await asyncio.gather(receive(), send())


async def send_one(url, command):
    """Send a single command and collect output briefly."""
    if url.startswith("https://"):
        url = "wss://" + url[len("https://"):]

    async with websockets.connect(url) as ws:
        await ws.send(b"\x03")  # Ctrl-C to interrupt
        await asyncio.sleep(0.3)
        await ws.send((command + "\r\n").encode())

        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=1.5)
                if isinstance(msg, bytes):
                    sys.stdout.write(msg.decode(errors="replace"))
                else:
                    sys.stdout.write(msg)
                sys.stdout.flush()
        except asyncio.TimeoutError:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python microbit_connect.py <url> [command]")
        sys.exit(1)
    url = sys.argv[1]
    if len(sys.argv) >= 3:
        asyncio.run(send_one(url, " ".join(sys.argv[2:])))
    else:
        asyncio.run(repl(url))
