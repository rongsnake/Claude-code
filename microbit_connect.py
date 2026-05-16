#!/usr/bin/env python3
"""
Connects to a micro:bit via the local bridge script over TCP (e.g. through ngrok).
Usage: python microbit_connect.py <host> <port>
       python microbit_connect.py 0.tcp.ngrok.io 12345
"""

import socket
import threading
import sys


class MicrobitConnection:
    def __init__(self, host, port):
        self.host = host
        self.port = int(port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        print(f"Connected to micro:bit at {host}:{port}")

    def send(self, text):
        self.sock.sendall((text + "\r\n").encode())

    def recv_loop(self, on_data):
        def _loop():
            buf = b""
            while True:
                try:
                    chunk = self.sock.recv(256)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        on_data(line.decode(errors="replace").rstrip())
                except Exception:
                    break
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def close(self):
        self.sock.close()


def interactive_repl(host, port):
    conn = MicrobitConnection(host, port)

    def print_output(line):
        print(f"  << {line}")

    conn.recv_loop(print_output)

    print("Type MicroPython commands. Ctrl+C to exit.\n")
    try:
        while True:
            try:
                line = input(">> ")
            except EOFError:
                break
            conn.send(line)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        print("\nDisconnected.")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        host, port = sys.argv[1], sys.argv[2]
    else:
        addr = input("Enter ngrok address (host:port): ").strip()
        host, port = addr.rsplit(":", 1)
    interactive_repl(host, port)
