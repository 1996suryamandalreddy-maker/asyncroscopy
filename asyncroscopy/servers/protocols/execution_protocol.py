"""
Executes locally registered commands.
Used by backend servers (AS, Gatan, CEOS, etc).
Packages responses in a standard format.
"""

from twisted.protocols.basic import Int32StringReceiver
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from asyncroscopy.servers.protocols.utils import package_message, unpackage_message

import json
import logging
import traceback
import inspect
import numpy as np

def get_protocol_logger(instance):
    cls = instance.__class__
    name = f"asyncroscopy.protocols.{cls.__name__}"
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Add a StreamHandler for terminal output
        ch = logging.StreamHandler()
        formatter = logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger

class ExecutionProtocol(Int32StringReceiver):
    """
    Protocol for executing registered commands.
    Command handling can be overridden in subclasses.
    """

    def __init__(self):
        super().__init__()

        # Create per-protocol logger
        self.log = get_protocol_logger(self)

        # Build a whitelist of allowed command names
        allowed = []
        for name, value in ExecutionProtocol.__dict__.items():
            if callable(value) and not name.startswith("_"):
                allowed.append(name)
        self.allowed_commands = set(allowed)

        # For awaiting proxy responses
        self._pendingCommands = {}

    # ----------------------------------------------------------------------
    # Connection events
    # ----------------------------------------------------------------------

    def connectionMade(self):
        peer = self.transport.getPeer()
        # self.log.info("Connection established from %s", peer)

    def connectionLost(self, reason):
        # self.log.info("Client disconnected: %s", reason.getErrorMessage())

        for d in self._pendingCommands.values():
            d.errback(reason)
        self._pendingCommands.clear()

    def disconnect(self):
        """Disconnect cleanly."""
        self.log.debug("Disconnect requested")
        self.transport.loseConnection()

    # ----------------------------------------------------------------------
    # Message handling
    # ----------------------------------------------------------------------

    def stringReceived(self, data: bytes):
        msg = data.decode().strip()
        self.log.debug("Received command: %s", msg)

        parts = msg.split()
        if not parts:
            self.log.warning("Received empty command")
            return

        cmd, *args = parts
        args_dict = dict(arg.split("=", 1) for arg in args if "=" in arg)

        try:
            method = getattr(self, cmd, None)
            if method is None:
                raise AttributeError(f"Unknown command '{cmd}'")

            result = method(args_dict)

            # Everything going back is bytes
            if not isinstance(result, (bytes, bytearray)):
                result = str(result).encode()

            self.sendString(result)
            self.log.debug("Sent response for command '%s'", cmd)

        except Exception:
            err = traceback.format_exc()
            self.log.error("Error executing '%s': %s", msg, err)
            self.sendString(err.encode())

    # ----------------------------------------------------------------------
    # Helpers for central
    # ----------------------------------------------------------------------

    def discover_commands(self, args=None):
        """Return JSON array of all public commands."""
        cmds = [
            name for name in dir(self)
            if not name.startswith("_") and callable(getattr(self, name))
        ]
        cmds.sort()
        self.sendString(package_message(json.dumps(cmds)))

    def get_help(self, args: dict):
        """Help on a specific command."""
        # args comes from the space-separated string, so first key is the command
        command_name = args.get('command_name')
        meth = getattr(self, command_name, None)
        if not meth or not callable(meth):
            result = {"error": f"Unknown command '{command_name}'"}
        else:
            sig = str(inspect.signature(meth))
            doc = inspect.getdoc(meth) or ""
            result = {
                "name": command_name,
                "signature": sig,
                "summary": doc.split("\n")[0] if doc else "",
                "doc": doc,
            }
        self.sendString(package_message(json.dumps(result)))
