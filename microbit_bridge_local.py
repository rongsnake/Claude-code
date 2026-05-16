#!/usr/bin/env python3
"""
Run this script on YOUR LOCAL MACHINE (not in the cloud).
It bridges the micro:bit serial port to a TCP socket.

Requirements: pip install pyserial
Then expose it: ngrok tcp 5678
"""

import serial
import serial.tools.list_ports
import socket
import threading
import sys

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


def bridge(ser, conn):
    def serial_to_socket():
        try:
            while True:
                data = ser.read(256)
                if data:
                    conn.sendall(data)
        except Exception:
            pass
        finally:
            conn.close()

    def socket_to_serial():
        try:
            while True:
                data = conn.recv(256)
                if not data:
                    break
                ser.write(data)
        except Exception:
            pass

    t1 = threading.Thread(target=serial_to_socket, daemon=True)
    t2 = threading.Thread(target=socket_to_serial, daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print("Client disconnected, waiting for next connection...")


def main():
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

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(1)

    print(f"\nBridge ready on port {PORT}")
    print("─" * 40)
    print("Now run in another terminal:")
    print("  ngrok tcp 5678")
    print("─" * 40)
    print("Then give Claude the ngrok host and port (e.g. 0.tcp.ngrok.io:12345)\n")

    while True:
        conn, addr = server.accept()
        print(f"Cloud connected from {addr}")
        bridge(ser, conn)


if __name__ == "__main__":
    main()
