# central_server.py
import json
import inspect
import logging
import socket
import struct
from typing import Dict, Tuple, Optional
from datetime import datetime

import numpy as np
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue, gatherResults
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.protocols.basic import Int32StringReceiver
from twisted.internet.protocol import Factory

from asyncroscopy.servers.protocols.utils import package_message, unpackage_message


# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("central")

# ---------- Defaults ----------
DEFAULT_ROUTING_TABLE = {
    "AS": ("localhost", 9001),
    "Gatan": ("localhost", 9002),
    "Ceos": ("localhost", 9003),
    "Preacquired_AS": ("localhost", 9004),
}


# ---------- BackendClient ----------
class BackendClient(Int32StringReceiver):
    """
    Lightweight protocol used by Central to talk to backends.
    Completes the provided Deferred with the raw framed response bytes.
    """
    MAX_LENGTH = 10_000_000

    def __init__(self, finished: Deferred):
        super().__init__()
        self.finished = finished

    def connectionMade(self):
        peer = self.transport.getPeer()
        log.debug("BackendClient connectionMade to %s", peer)

    def stringReceived(self, data: bytes):
        if not self.finished.called:
            self.finished.callback(data)
        # close transport after receiving
        try:
            self.transport.loseConnection()
        except Exception:
            pass

    def connectionLost(self, reason):
        if not self.finished.called:
            self.finished.errback(reason)

    def sendCommand(self, cmd: str):
        """Send a framed command to backend using Int32 framing used by Int32StringReceiver."""
        log.debug("Central → Exec: %s", cmd)
        self.sendString(cmd.encode("utf-8"))

# ---------- CentralProtocol ----------
class CentralProtocol(Int32StringReceiver):
    MAX_LENGTH = 10_000_000

    def __init__(self, routing_table: Optional[Dict[str, Tuple[str,int]]] = None):
        super().__init__()
        self.routing_table = factory.routing_table

    def connectionMade(self):
        peer = self.transport.getPeer()
        log.info("[Central] Connection made from %s", peer)

    def connectionLost(self, reason):
        log.info("[Central] Connection ended") # : %s", reason

    def stringReceived(self, data: bytes):
        """Main entry point for incoming client/backend messages."""
        try:
            msg = data.decode("utf-8").strip()
        except Exception:
            # If decode fails, send standardized error
            self.sendString(package_message("[Central] Invalid UTF-8 in request"))
            return

        log.info("[Central] Received command: %s", msg)

        # 1) Central_* messages (handled by subclass override if present)
        if msg.startswith("Central_"):
            handled = self._handle_central_command(msg)
            if not handled:
                self.sendString(package_message(f"[Central] Unknown central command: {msg.split()[0][8:]}"))
            return

        # 2) Route to backend if prefix matches (prefix_...)
        if self._route_if_backend_message(msg):
            return

        # 3) Unknown command
        self.sendString(package_message(f"Unknown command prefix in '{msg}'"))

    # ----- routing helpers -----
    def _route_if_backend_message(self, msg: str) -> bool:
        """
        If msg starts with a registered prefix (e.g. "AS_..."), forward to that backend.
        Returns True if a route was found and forwarding started.
        """
        for prefix, (host, port) in self.routing_table.items():
            if msg.startswith(prefix + "_"):
                routed_cmd = msg[len(prefix) + 1 :]
                log.info("[Central] Routing '%s' to %s backend at %s:%d", msg, prefix, host, port)
                self._forward_to_backend(host, port, routed_cmd)
                return True
        return False

    def _handle_central_command(self, msg: str) -> bool:
        parts = msg.split()
        if not parts:
            return False
        cmd_name = parts[0]
        if cmd_name == "Central_set_routing_table":
            try:
                # Re-assemble split tokens like  AS=('127.0.0.1', 9001)
                cleaned, buf = [], []
                for tok in parts[1:]:
                    buf.append(tok)
                    if tok.endswith(")"):
                        cleaned.append(" ".join(buf))
                        buf = []

                routing_table = {}
                for item in cleaned:
                    k, v = item.split("=", 1)
                    inner = v.strip()[1:-1] # remove ( )
                    host_part, port_part = inner.split(",", 1)
                    host = host_part.strip().strip("'\"")
                    port = int(port_part.strip())
                    routing_table[k.strip()] = (host, port)
                    print(routing_table)
                self.set_routing_table(routing_table)
                self.sendString(package_message("[Central] Routing table updated"))
            except Exception as e:
                log.exception("Failed to set routing table")
                self.sendString(package_message(f"[Central ERROR] {e}"))
            return True

        return False

    def _parse_routing_table(self, tokens):
        """
        Parse incoming routing-table tokens. Accepts either:
          - JSON string (single token) e.g. '{"AS":["host",9001], ...}'
          - Legacy tokens like: AS=('localhost', 9001) Gatan=('localhost', 9002)
        Returns dict mapping key -> (host, port)
        """
        # try JSON first if only one token and looks like JSON
        if len(tokens) == 1:
            t = tokens[0].strip()
            if (t.startswith("{") and t.endswith("}")) or (t.startswith('"') and t.endswith('"')):
                try:
                    parsed = json.loads(t)
                    # normalize to tuple(host,port)
                    out = {}
                    for k, v in parsed.items():
                        if isinstance(v, (list, tuple)) and len(v) >= 2:
                            out[k] = (v[0], int(v[1]))
                        else:
                            raise ValueError("Invalid JSON routing entry for %s" % k)
                    return out
                except Exception:
                    # fall through to legacy parsing
                    pass

        # legacy parsing: tokens might be split, reassemble chunks that end with ')'
        chunks, buf = [], []
        for tok in tokens:
            buf.append(tok)
            if tok.endswith(")"):
                chunks.append(" ".join(buf))
                buf = []
        table = {}
        for item in chunks:
            key, val = item.split("=", 1)
            inner = val.strip()
            if inner.startswith("(") and inner.endswith(")"):
                inner = inner[1:-1]
            # split on first comma
            host_str, port_str = inner.split(",", 1)
            host = host_str.strip().strip("'\"")
            port = int(port_str.strip())
            table[key.strip()] = (host, port)
        return table

    def set_routing_table(self, routing_table: Dict[str, Tuple[str,int]]):
        self.routing_table = routing_table
        factory.routing_table = routing_table
        log.info("Routing table updated: %s", self.routing_table)

    # ----- connection/send helpers -----
    def _connect_and_send(self, host: str, port: int, command: str, timeout: Optional[float] = 5.0) -> Deferred:
        """
        Connect to a backend and send a framed command.
        Returns a Deferred that fires with the raw framed reply bytes from backend (not yet unpacked).
        """
        d = Deferred()
        endpoint = TCP4ClientEndpoint(reactor, host, port, timeout=timeout)

        backend_proto = BackendClient(d)

        def on_connect(proto):
            try:
                proto.sendCommand(command)
            except Exception as exc:
                if not d.called:
                    d.errback(exc)
                return d
            return d

        conn_d = connectProtocol(endpoint, backend_proto)
        conn_d.addCallback(on_connect)
        conn_d.addErrback(lambda f: d.errback(f))
        return d

    def _forward_to_backend(self, host: str, port: int, command: str):
        """
        Forward a command to a backend and automatically send the response back to the client.
        Returns the Deferred created by _connect_and_send.
        """
        d = self._connect_and_send(host, port, command)

        def on_success(payload_bytes):
            # payload_bytes is already a framed package from the backend; send directly
            log.info("[Central] Received backend response (len=%d)", len(payload_bytes))
            try:
                self.sendString(payload_bytes)
            except Exception:
                log.exception("Failed to send backend response to client")

        def on_error(failure):
            log.error("Error talking to backend: %s", failure)
            try:
                self.sendString(package_message(f"[Central ERROR] {failure}"))
            except Exception:
                log.exception("Failed to send error to client")

        d.addCallback(on_success)
        d.addErrback(on_error)
        return d

    # Exposed for SmartProxy / orchestration: returns Deferred with backend raw bytes
    def _ask_backend(self, prefix: str, command: str) -> Deferred:
        if prefix not in self.routing_table:
            raise ValueError(f"No backend named '{prefix}'")
        host, port = self.routing_table[prefix]
        return self._connect_and_send(host, port, command)

# ---------- Factory ----------
class CentralFactory(Factory):
    def __init__(self, routing_table= DEFAULT_ROUTING_TABLE):
        super().__init__()
        self.routing_table = routing_table
        self.protocol = CentralProtocol

    def buildProtocol(self, addr):
        return self.protocol(routing_table=self.routing_table)

# ---------- Run server ----------
if __name__ == "__main__":
    log.info("Central server running on port 9000...")
    factory = CentralFactory(routing_table=DEFAULT_ROUTING_TABLE)
    reactor.listenTCP(9000, factory)
    reactor.run()