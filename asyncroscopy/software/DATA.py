"""DATA Tango device.

This device is the Tango bridge to the Tiled HTTP data server. It stores the
server URI, acquisition save path, and API key used by notebooks and microscope
devices.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import numpy as np
from tango import AttrWriteType, DevState
from tango.server import Device, attribute, command

DEFAULT_TILED_URI = "http://10.46.217.241:9091"
DEFAULT_ACQUISITION_DIR = "outputs/tiled_acquisitions"


def saved_path_candidates(saved_path: str, save_directory: str, tiled_root_path: str = "") -> list[str]:
    saved = str(saved_path).replace("\\", "/")
    save_root = str(save_directory).replace("\\", "/").rstrip("/")
    root = tiled_root_path.strip("/")
    relative = saved[len(save_root) + 1 :] if save_root and saved.lower().startswith(save_root.lower() + "/") else _path_name(saved)
    candidates = _tiled_path_candidates(relative, root)
    if _path_name(saved) != relative:
        candidates.extend(_tiled_path_candidates(_path_name(saved), root))
    return list(dict.fromkeys(candidate.strip("/") for candidate in candidates if candidate))


def connect_tiled_client(uri: str | None = None, api_key: str | None = None):
    from tiled.client import from_uri

    uri = uri or os.environ.get("ASYNCROSCOPY_TILED_URI") or DEFAULT_TILED_URI
    api_key = api_key if api_key is not None else os.environ.get("TILED_API_KEY")
    return from_uri(uri, **({"api_key": api_key} if api_key else {}))


class DATA(Device):
    """Tango bridge to the Tiled HTTP data server."""

    host = attribute(
        label="Tiled Host",
        dtype=str,
        access=AttrWriteType.READ_WRITE,
        doc="Hostname or IP address for the Tiled HTTP data server.",
    )
    port = attribute(
        label="Tiled Port",
        dtype=int,
        access=AttrWriteType.READ_WRITE,
        doc="TCP port for the Tiled HTTP data server.",
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
    tiled_server = attribute(
        label="Tiled Server",
        dtype=str,
        access=AttrWriteType.READ,
        doc="yes if the configured Tiled HTTP data server responds, otherwise no.",
    )

    def init_device(self) -> None:
        Device.init_device(self)
        self.set_state(DevState.ON)
        self._host, self._port = self._parse_uri(os.environ.get("ASYNCROSCOPY_TILED_URI", DEFAULT_TILED_URI))
        self._save_path = os.environ.get("ASYNCROSCOPY_ACQUISITION_DIR", DEFAULT_ACQUISITION_DIR)
        self._root_path = os.environ.get("ASYNCROSCOPY_TILED_ROOT_PATH", "").strip("/")
        self._api_key = os.environ.get("TILED_API_KEY")
        self._tiled_process = None
        self._tiled_server = "yes" if self._tiled_alive() else "no"
        self._tiled_server_status = ""
        self.info_stream("DATA device initialised")

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

    def read_tiled_server(self) -> str:
        self._tiled_server = "yes" if self._tiled_alive() else "no"
        return self._tiled_server

    @command(dtype_out=str)
    def get_uri(self) -> str:
        return self._uri()

    @command(dtype_out=str)
    def get_config(self) -> str:
        return json.dumps(self._config())

    @command(dtype_in=str, dtype_out=str)
    def configure(self, config_json: str) -> str:
        config = json.loads(config_json) if config_json else {}
        for key, writer in {
            "host": self.write_host,
            "port": self.write_port,
            "save_path": self.write_save_path,
            "root_path": self.write_root_path,
        }.items():
            if key in config:
                writer(config[key])
        return self.get_config()

    @command(dtype_in=str, dtype_out=str)
    def set_api_key(self, api_key: str) -> str:
        self._api_key = api_key
        return self.get_config()

    @command(dtype_out=str)
    def clear_api_key(self) -> str:
        self._api_key = None
        return self.get_config()

    @command(dtype_out=str)
    def start_tiled_server(self) -> str:
        if self._tiled_alive():
            self._tiled_server = "yes"
            return self.get_config()

        catalog = _path_text(Path(self._save_path).expanduser() / ".asyncroscopy_tiled_catalog.db")
        api_key = self._api_key or os.environ.get("TILED_API_KEY", "secret")
        try:
            if not (_looks_like_windows_drive_path(self._save_path) and os.name != "nt"):
                Path(self._save_path).expanduser().mkdir(parents=True, exist_ok=True)
            subprocess.run([self._tiled_executable(), "catalog", "init", "--if-not-exists", catalog], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except Exception as exc:
            self._tiled_server = "no"
            self._tiled_server_status = str(exc)
            return self.get_config()

        command = [
            self._tiled_executable(),
            "serve",
            "catalog",
            catalog,
            "--read",
            self._save_path,
            "--public",
            "--api-key",
            api_key,
            "--host",
            self._host,
            "--port",
            str(self._port),
        ]
        self._tiled_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not self._tiled_alive():
            if self._tiled_process.poll() is not None:
                break
            time.sleep(0.5)
        self._tiled_server = "yes" if self._tiled_alive() else "no"
        output = "" if self._tiled_process.poll() is None or self._tiled_process.stdout is None else self._tiled_process.stdout.read()
        if self._tiled_server == "yes":
            register = [self._tiled_executable(), "register", self._uri(), self._save_path, "--api-key", api_key, "--keep-ext"]
            result = subprocess.run(register, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self._tiled_server_status = "running; registered" if result.returncode == 0 else f"running; register failed; {result.stdout[-1000:]}"
        else:
            self._tiled_server_status = f"not running; exit_code={self._tiled_process.poll()}; {output[-1000:]}"
        return self.get_config()

    @command(dtype_in=str, dtype_out=str)
    def list_entries(self, path: str = "") -> str:
        return json.dumps({"path": path, "entries": list(self._walk_path(self._client(), path))})

    @command(dtype_out=str)
    def list_root(self) -> str:
        return self.list_entries("")

    @command(dtype_in=str, dtype_out=str)
    def get_data(self, saved_path_or_tiled_path: str) -> str:
        return json.dumps(self._json_ready(self._read_node(self._node_for_path_or_saved_path(saved_path_or_tiled_path))))

    @command(dtype_in=str, dtype_out=str)
    def get_unique_id(self, saved_path: str) -> str:
        candidates = saved_path_candidates(saved_path.strip(), self._save_path, self._root_path)
        return candidates[0] if candidates else _path_name(saved_path)

    @command(dtype_out=str)
    def get_recent(self) -> str:
        return json.dumps({"save_path": self._save_path, "files": self._recent_files()})

    @command(dtype_in=str, dtype_out=str)
    def path_exists(self, path: str) -> str:
        is_windows_path = _looks_like_windows_drive_path(path)
        candidate = PureWindowsPath(path) if is_windows_path else Path(path).expanduser()
        if not is_windows_path and not candidate.is_absolute():
            candidate = Path(self._save_path).expanduser() / candidate

        exists = False if is_windows_path and os.name != "nt" else Path(candidate).exists()
        return json.dumps(
            {
                "path": _path_text(candidate),
                "exists": exists,
                "is_file": Path(candidate).is_file() if exists else False,
                "size_bytes": Path(candidate).stat().st_size if exists and Path(candidate).is_file() else None,
                "note": "Windows drive path cannot be checked from this non-Windows process." if is_windows_path and os.name != "nt" else "",
            }
        )

    def _config(self) -> dict[str, Any]:
        return {
            "host": self._host,
            "port": self._port,
            "uri": self._uri(),
            "save_path": self._save_path,
            "root_path": self._root_path,
            "api_key_configured": bool(self._api_key),
            "tiled_server": self._tiled_server,
            "tiled_server_status": self._tiled_server_status,
        }

    def _uri(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _client(self):
        return connect_tiled_client(self._uri(), api_key=self._api_key)

    def _tiled_alive(self) -> bool:
        try:
            with urlopen(self._uri(), timeout=0.3):
                return True
        except (OSError, URLError):
            return False

    def _node_for_path_or_saved_path(self, saved_path_or_tiled_path: str):
        client = self._client()
        candidates = [saved_path_or_tiled_path.strip(), *saved_path_candidates(saved_path_or_tiled_path.strip(), self._save_path, self._root_path)]
        errors = []
        for candidate in list(dict.fromkeys(candidates)):
            try:
                return self._walk_path(client, candidate)
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
        raise KeyError("Could not resolve path in Tiled. Tried: " + "; ".join(errors))

    @staticmethod
    def _walk_path(node, tiled_path: str):
        for part in [piece for piece in tiled_path.strip("/").split("/") if piece]:
            node = node[part]
        return node

    @staticmethod
    def _read_node(node):
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

        files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)
        return [
            {
                "path": str(path),
                "file_name": path.name,
                "relative_path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "modified_time": path.stat().st_mtime,
            }
            for path in files[:20]
        ]

    @staticmethod
    def _json_ready(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return {"type": "ndarray", "dtype": str(value.dtype), "shape": list(value.shape), "data": value.tolist()}
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, bytes):
            return {"type": "bytes", "encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if isinstance(value, dict):
            return {str(key): DATA._json_ready(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [DATA._json_ready(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _parse_uri(uri: str) -> tuple[str, int]:
        without_scheme = uri.split("://", 1)[-1].strip("/")
        host, _, port = without_scheme.partition(":")
        return host or "10.46.217.241", int(port or 9091)

    @staticmethod
    def _tiled_executable() -> str:
        candidate = Path(sys.executable).with_name("tiled")
        return str(candidate) if candidate.exists() else "tiled"


def _tiled_path_candidates(relative_path: str, root_path: str = "") -> list[str]:
    path = Path(relative_path)
    candidates = [str(path.with_suffix("")).replace(os.sep, "/"), str(path).replace(os.sep, "/")]
    return [f"{root_path}/{candidate}" if root_path else candidate for candidate in dict.fromkeys(candidates)]


def _looks_like_windows_drive_path(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[0].isalpha() and value[2] in {"\\", "/"}


def _is_windows_drive_path(path: Path | PureWindowsPath) -> bool:
    return isinstance(path, PureWindowsPath) or _looks_like_windows_drive_path(str(path))


def _path_text(path: Path | PureWindowsPath) -> str:
    return str(path).replace("\\", "/") if _is_windows_drive_path(path) else str(path)


def _path_name(path: str) -> str:
    return PureWindowsPath(path).name if _looks_like_windows_drive_path(path) else Path(path).name


if __name__ == "__main__":
    DATA.run_server()
