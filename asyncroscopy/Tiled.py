"""Tiled Tango device.

This device owns notebook-facing access to the Tiled server. Acquisition
commands return saved file paths, and notebooks can pass those paths to this
device to resolve and read data through Tiled.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path, PureWindowsPath
from typing import Any

import numpy as np
from tango import AttrWriteType, DevState
from tango.server import Device, attribute, command

from asyncroscopy.tiled_helpers import (
    DEFAULT_ACQUISITION_DIR,
    DEFAULT_TILED_URI,
    connect_tiled_client,
    saved_path_candidates,
)


class Tiled(Device):
    """Tiled server access device."""

    # ------------------------------------------------------------------
    # Attributes
    # ------------------------------------------------------------------

    host = attribute(
        label="Tiled Host",
        dtype=str,
        access=AttrWriteType.READ_WRITE,
        doc="Hostname or IP address for the Tiled server.",
    )

    port = attribute(
        label="Tiled Port",
        dtype=int,
        access=AttrWriteType.READ_WRITE,
        doc="TCP port for the Tiled server.",
    )

    save_path = attribute(
        label="Acquisition Save Path",
        dtype=str,
        access=AttrWriteType.READ_WRITE,
        doc="Directory where acquisition files are written and served by Tiled.",
    )

    root_path = attribute(
        label="Tiled Root Path",
        dtype=str,
        access=AttrWriteType.READ_WRITE,
        doc="Optional path prefix inside Tiled corresponding to save_path.",
    )

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_device(self) -> None:
        Device.init_device(self)
        self.set_state(DevState.ON)

        uri = os.environ.get("ASYNCROSCOPY_TILED_URI", DEFAULT_TILED_URI)
        host, port = self._parse_uri(uri)

        self._host: str = host
        self._port: int = port
        self._save_path: str = os.environ.get("ASYNCROSCOPY_ACQUISITION_DIR", DEFAULT_ACQUISITION_DIR)
        self._root_path: str = os.environ.get("ASYNCROSCOPY_TILED_ROOT_PATH", "").strip("/")
        self._api_key: str | None = os.environ.get("TILED_API_KEY")
        self.info_stream("Tiled device initialised")

    # ------------------------------------------------------------------
    # Attribute read / write
    # ------------------------------------------------------------------

    def read_host(self) -> str:
        return self._host

    def write_host(self, value: str) -> None:
        self._host = value.strip()

    def read_port(self) -> int:
        return self._port

    def write_port(self, value: int) -> None:
        self._port = int(value)

    def read_save_path(self) -> str:
        return self._save_path

    def write_save_path(self, value: str) -> None:
        self._save_path = value

    def read_root_path(self) -> str:
        return self._root_path

    def write_root_path(self, value: str) -> None:
        self._root_path = value.strip("/")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @command(dtype_out=str)
    def get_uri(self) -> str:
        """Return the configured Tiled server URI."""
        return self._uri()

    @command(dtype_out=str)
    def get_config(self) -> str:
        """Return the active Tiled device config as JSON."""
        return json.dumps(self._config())

    @command(dtype_in=str, dtype_out=str)
    def configure(self, config_json: str) -> str:
        """Update host, port, save_path, and root_path from a JSON object."""
        config = json.loads(config_json) if config_json else {}
        if "host" in config:
            self.write_host(config["host"])
        if "port" in config:
            self.write_port(config["port"])
        if "save_path" in config:
            self.write_save_path(config["save_path"])
        if "root_path" in config:
            self.write_root_path(config["root_path"])
        return self.get_config()

    @command(dtype_in=str, dtype_out=str)
    def set_api_key(self, api_key: str) -> str:
        """Set the API key used by this Tango device to connect to Tiled."""
        self._api_key = api_key
        return self.get_config()

    @command(dtype_out=str)
    def clear_api_key(self) -> str:
        """Clear the API key used by this Tango device to connect to Tiled."""
        self._api_key = None
        return self.get_config()

    @command(dtype_in=str, dtype_out=str)
    def list_entries(self, path: str = "") -> str:
        """List entries below a Tiled path."""
        node = self._node_for_path(path)
        return json.dumps({"path": path, "entries": list(node)})

    @command(dtype_out=str)
    def list_root(self) -> str:
        """List entries at the Tiled root."""
        return self.list_entries("")

    @command(dtype_in=str, dtype_out=str)
    def get_data(self, saved_path_or_tiled_path: str) -> str:
        """Read data from Tiled using a saved file path or Tiled path."""
        node = self._node_for_path_or_saved_path(saved_path_or_tiled_path)
        data = self._read_node(node)
        return json.dumps(self._json_ready(data))

    @command(dtype_out=str)
    def get_recent(self) -> str:
        """Return recently modified files in save_path as JSON."""
        return json.dumps({"save_path": self._save_path, "files": self._recent_files()})

    @command(dtype_in=str, dtype_out=str)
    def path_exists(self, path: str) -> str:
        """Return file existence details as seen by this Tango device process."""
        is_windows_path = self._looks_like_windows_drive_path(path)
        candidate = PureWindowsPath(path) if is_windows_path else Path(path).expanduser()
        if not is_windows_path and not candidate.is_absolute():
            candidate = Path(self._save_path).expanduser() / candidate

        exists = False if is_windows_path and os.name != "nt" else Path(candidate).exists()
        return json.dumps(
            {
                "path": str(candidate).replace("\\", "/"),
                "exists": exists,
                "is_file": Path(candidate).is_file() if exists else False,
                "size_bytes": Path(candidate).stat().st_size if exists and Path(candidate).is_file() else None,
                "note": "Windows drive path cannot be checked from this non-Windows process." if is_windows_path and os.name != "nt" else "",
            }
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _config(self) -> dict[str, Any]:
        return {
            "host": self._host,
            "port": self._port,
            "uri": self._uri(),
            "save_path": self._save_path,
            "root_path": self._root_path,
            "api_key_configured": bool(self._api_key),
        }

    def _uri(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _client(self):
        return connect_tiled_client(self._uri(), api_key=self._api_key)

    def _node_for_path_or_saved_path(self, saved_path_or_tiled_path: str):
        text = saved_path_or_tiled_path.strip()
        client = self._client()
        candidates = [text]
        candidates.extend(saved_path_candidates(text, self._save_path, self._root_path))
        errors = []
        for candidate in list(dict.fromkeys(candidates)):
            try:
                return self._walk_path(client, candidate)
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
        raise KeyError("Could not resolve path in Tiled. Tried: " + "; ".join(errors))

    def _node_for_path(self, tiled_path: str):
        return self._walk_path(self._client(), tiled_path)

    @staticmethod
    def _walk_path(node, tiled_path: str):
        for part in [piece for piece in tiled_path.strip("/").split("/") if piece]:
            node = node[part]
        return node

    def _read_node(self, node):
        if hasattr(node, "read"):
            return node.read()
        try:
            return node[:]
        except Exception:
            return node

    def _recent_files(self) -> list[dict[str, Any]]:
        root = Path(self._save_path).expanduser()
        if not root.exists():
            return []

        files = [path for path in root.rglob("*") if path.is_file()]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        recent = []
        for path in files[:20]:
            stat = path.stat()
            recent.append(
                {
                    "path": str(path),
                    "file_name": path.name,
                    "relative_path": str(path.relative_to(root)),
                    "size_bytes": stat.st_size,
                    "modified_time": stat.st_mtime,
                }
            )
        return recent

    @staticmethod
    def _json_ready(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return {
                "type": "ndarray",
                "dtype": str(value.dtype),
                "shape": list(value.shape),
                "data": value.tolist(),
            }
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, bytes):
            return {
                "type": "bytes",
                "encoding": "base64",
                "data": base64.b64encode(value).decode("ascii"),
            }
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if isinstance(value, dict):
            return {str(key): Tiled._json_ready(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [Tiled._json_ready(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _parse_uri(uri: str) -> tuple[str, int]:
        without_scheme = uri.split("://", 1)[-1].strip("/")
        host, _, port = without_scheme.partition(":")
        return host or "10.46.217.241", int(port or 9091)

    @staticmethod
    def _looks_like_windows_drive_path(value: str) -> bool:
        return len(value) >= 3 and value[1] == ":" and value[0].isalpha() and value[2] in {"\\", "/"}


# ----------------------------------------------------------------------
# Server entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    Tiled.run_server()
