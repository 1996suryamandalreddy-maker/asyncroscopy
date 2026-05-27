# Gatan_server_twin.py

"""
mirrors the real thing.
"""

from twisted.internet import reactor, protocol
import numpy as np
import time
import sys

from asyncroscopy.servers.protocols.execution_protocol import ExecutionProtocol
from asyncroscopy.servers.protocols.utils import package_message, unpackage_message


# FACTORY — holds shared state (persistent across all connections)
class GatanFactory(protocol.Factory):
    def __init__(self):
        # persistent states for all protocol instances
        self.detectors = {}
        self.status = "Offline"

    def buildProtocol(self, addr):
        """Create a new protocol instance and attach the factory (shared state)."""
        proto = GatanProtocol()
        proto.factory = self
        return proto


# PROTOCOL — handles per-connection command execution
class GatanProtocol(ExecutionProtocol):
    def __init__(self):
        super().__init__()

    def connect_Gatan(self, args: dict):
        """Connect to the Gatan camera via Gatan"""
        self.factory.status = "Ready"
        msg = "[Gatan] Connected to Gatan."
        self.sendString(package_message(msg))

    def get_spectrum(self, args: dict):
        """Simulate a core-loss eels spectrum"""
        size = args.get('size')
        size = int(size)
        time.sleep(3)

        x = np.arange(size)
        spectrum = (np.exp(-x / 200) * 1000
         + 50 * np.exp(-0.5 * ((x - 150) / 5) ** 2)
         + 30 * np.exp(-0.5 * ((x - 300) / 8) ** 2)
         + np.random.normal(0, 5, size)).astype(np.float32)
        print(package_message(spectrum))

        self.sendString(package_message(spectrum))

    def get_status(self, args=None):
        """Return the status"""
        msg = f"Gatan server is {self.factory.status}"
        self.sendString(package_message(msg))


if __name__ == "__main__":
    port = 9002
    print(f"[Gatan] Server running on port {port}...")
    reactor.listenTCP(port, GatanFactory())
    reactor.run()