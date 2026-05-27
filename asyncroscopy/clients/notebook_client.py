'''
Client for TEM central server.
Notebook-side client for the Central TEM server.

Compatible with:
 - Int32StringReceiver framing
 - package_message() / unpackage_message() protocol
 - Backend routing (AS_get..., Gatan_get..., etc.)
 - Central orchestration commands (Central_*)
'''

import socket
import struct
import numpy as np
import threading
from typing import List, Dict, Any, Tuple, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from asyncroscopy.servers.protocols.utils import package_message, unpackage_message

class NotebookClient:
    """Client for TEM central server."""

    def __init__(self, host="localhost", port=9000):
        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="Client")
        self.host = host
        self.port = port

    @classmethod
    def connect(cls, host="127.0.0.1", port=9000):
        """Try to connect briefly to verify central server is up."""
        print(f"Connecting to central server {host}:{port}...")
        try:
            with socket.create_connection((host, port), timeout=5):
                print("Connected to central server.")
            return cls(host, port)
        except (ConnectionRefusedError, socket.timeout):
            print(f"Could not connect to central server at {host}:{port}")
            return None

    def send_command(self, destination: str, command: str,
                     args: dict | None = None,
                     timeout: float | None = None):
        """Send command + args, return decoded response payload."""
        if args is None:
            args = {}

        cmd = f"{destination}_{command} " + " ".join(f"{k}={v}" for k, v in args.items())
        payload = cmd.encode()
        header = struct.pack("!I", len(payload))
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout) as sock:
                # Send
                sock.sendall(header + payload)
                # Receive 4-byte response header
                resp_hdr = self._recv_exact(sock, 4)
                resp_len = struct.unpack("!I", resp_hdr)[0]
                # Receive payload
                data = self._recv_exact(sock, resp_len)
                dtype, shape, payload = unpackage_message(data)

                return payload

        except (ConnectionRefusedError, socket.timeout):
            print(f"Could not connect to {self.host}:{self.port} after {timeout} seconds")
            return None

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        """Receive exactly n bytes."""
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Socket closed early")
            buf += chunk
        return buf

    def send_parallel_commands(
        self,
        commands: Sequence[Tuple[str, str, dict | None]],
        timeout: float = 30.0
    ) -> List[Any]:
        """
        Send many commands in parallel (fire-and-forget style, but ordered results).

        Example:
            results = client.send_parallel_commands([
                ("AS",   "get_stage", {}),
                ("Ceos", "GetMagnification", {}),
                ("AS",   "get_beam_current", {}),
                ("Gatan", "CameraAcquire", {"exposure": 0.1}),
            ])

            stage, mag, current, image = results   # ← same order!

        Returns list of decoded payloads (or None on failure).
        """
        if not commands:
            return []

        futures = []
        for dest, cmd, args in commands:
            future = self.executor.submit(
                self.send_command,
                destination=dest,
                command=cmd,
                args=args or {},
                timeout=timeout
            )
            futures.append(future)

        # Preserve original order
        results = []
        for future in as_completed(futures):
            # Find which index this future belongs to
            idx = futures.index(future)
            try:
                results.append((idx, future.result()))
            except Exception as e:
                results.append((idx, e))

        # Sort by original index and extract values
        results.sort(key=lambda x: x[0])
        return [r if not isinstance(r, Exception) else None for _, r in results]