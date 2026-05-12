"""Helpers for saving AutoScript acquisitions and resolving them through Tiled."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any


DEFAULT_TILED_URI = "http://10.46.217.241:9091"
DEFAULT_ACQUISITION_DIR = "outputs/tiled_acquisitions"


def acquisition_config(
    *,
    save_directory: str | os.PathLike[str] | None = None,
    file_format: str | None = None,
) -> dict[str, str]:
    """Build a normalized acquisition save config."""
    return {
        "save_directory": str(
            save_directory
            or os.environ.get("ASYNCROSCOPY_ACQUISITION_DIR")
            or DEFAULT_ACQUISITION_DIR
        ),
        "file_format": (file_format or os.environ.get("ASYNCROSCOPY_ACQUISITION_FORMAT") or "tiff").lower().lstrip("."),
    }


def configure_tiled_acquisition(
    microscope_proxy: Any,
    *,
    save_directory: str | os.PathLike[str],
    file_format: str = "tiff",
) -> dict[str, str]:
    """Configure a ThermoMicroscope proxy for path-returning acquisitions."""
    config = acquisition_config(
        save_directory=save_directory,
        file_format=file_format,
    )
    response = microscope_proxy.configure_tiled_acquisition(json.dumps(config))
    return json.loads(response)


def save_adorned_acquisition(
    adorned: Any,
    *,
    acquisition_type: str,
    detector: str,
    config: dict[str, str],
) -> str:
    """Save an AutoScript adorned object and return the saved file path."""
    save_directory = _path_from_user(config["save_directory"])
    if isinstance(save_directory, Path):
        save_directory.mkdir(parents=True, exist_ok=True)
        _verify_writable_directory(save_directory)

    file_format = config.get("file_format", "tiff").lower().lstrip(".")
    if file_format not in {"tiff", "tif"}:
        raise ValueError(f"Unsupported acquisition file format: {file_format}")

    suffix = ".tiff"
    timestamp = time.time()
    file_name = f"{_safe_name(acquisition_type)}_{_safe_name(detector)}_{_stamp(timestamp)}_{uuid.uuid4().hex[:8]}{suffix}"
    path = save_directory / file_name

    path = _save_with_native_adorned_writer(adorned, path)

    if not _path_exists(path):
        if not (_is_windows_drive_path(path) and os.name != "nt"):
            raise FileNotFoundError(
                "Acquisition save returned without creating a file. "
                f"Expected path: {_path_text(path)}. "
                f"Save directory: {_path_text(save_directory)}. "
                f"Process working directory: {Path.cwd()}."
            )

    return _path_text(path)


def tiled_path_candidates(relative_path: str, tiled_root_path: str = "") -> list[str]:
    """Return likely Tiled paths for a saved file.

    Tiled directory registration commonly strips filename extensions unless
    the server is started with ``--keep-ext``. Include both forms.
    """
    path = Path(relative_path)
    without_suffix = str(path.with_suffix("")).replace(os.sep, "/")
    with_suffix = str(path).replace(os.sep, "/")
    root = tiled_root_path.strip("/")
    candidates = [without_suffix, with_suffix]
    if root:
        candidates = [f"{root}/{candidate}" for candidate in candidates]
    return list(dict.fromkeys(candidates))


def saved_path_candidates(saved_path: str, save_directory: str, tiled_root_path: str = "") -> list[str]:
    """Return likely Tiled paths for a saved file path."""
    saved = _normalize_path_string(saved_path)
    save_root = _normalize_path_string(save_directory).rstrip("/")
    root = tiled_root_path.strip("/")

    if save_root and saved.lower().startswith(save_root.lower() + "/"):
        relative = saved[len(save_root) + 1 :]
    else:
        relative = _path_name(PureWindowsPath(saved) if _looks_like_windows_drive_path(saved) else Path(saved))

    candidates = tiled_path_candidates(relative, root)
    filename = _path_name(PureWindowsPath(saved) if _looks_like_windows_drive_path(saved) else Path(saved))
    if filename != relative:
        candidates.extend(tiled_path_candidates(filename, root))
    return list(dict.fromkeys(candidate.strip("/") for candidate in candidates if candidate))


def connect_tiled_client(uri: str | None = None, api_key: str | None = None):
    """Connect to a Tiled server using the same API-key pattern as notebooks."""
    from tiled.client import from_uri

    uri = uri or os.environ.get("ASYNCROSCOPY_TILED_URI") or DEFAULT_TILED_URI
    api_key = api_key if api_key is not None else os.environ.get("TILED_API_KEY")
    kwargs = {"api_key": api_key} if api_key else {}
    return from_uri(uri, **kwargs)


def _save_with_native_adorned_writer(adorned: Any, path: Path | PureWindowsPath) -> Path | PureWindowsPath:
    result = adorned.save(_path_text(path))
    saved_path = _find_saved_path(path)
    if saved_path is not None:
        return saved_path
    if _is_windows_drive_path(path) and os.name != "nt":
        return path
    raise FileNotFoundError(
        "AutoScript adorned.save returned without creating the expected file. "
        f"Expected path: {_path_text(path)}. "
        f"Return value: {result!r}. "
        f"Directory contents: {_directory_preview(path.parent)}"
    )


def _find_saved_path(path: Path | PureWindowsPath) -> Path | PureWindowsPath | None:
    candidates = [path]
    suffix = _path_suffix(path)
    if suffix.lower() == ".tiff":
        candidates.append(path.with_suffix(".tif"))
    if suffix:
        candidates.append(path.with_suffix(""))
    for candidate in candidates:
        if _path_exists(candidate):
            return candidate
    return None


def _verify_writable_directory(path: Path) -> None:
    try:
        with tempfile.NamedTemporaryFile(prefix=".asyncroscopy_write_test_", dir=path, delete=True):
            pass
    except Exception as exc:
        raise PermissionError(f"Acquisition save directory is not writable: {path}") from exc


def _directory_preview(path: Path, limit: int = 10) -> list[str]:
    try:
        entries = sorted(path.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
        return [entry.name for entry in entries[:limit]]
    except Exception as exc:
        return [f"<could not list {path}: {exc}>"]


def _safe_name(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in str(value).strip().lower())
    return safe.strip("_") or "acquisition"


def _stamp(timestamp: float) -> str:
    return time.strftime("%Y%m%dT%H%M%S", time.localtime(timestamp))


def _path_from_user(value: str | os.PathLike[str]) -> Path | PureWindowsPath:
    text = os.fspath(value)
    if _looks_like_windows_drive_path(text):
        return PureWindowsPath(text)
    return Path(text).expanduser().resolve()


def _looks_like_windows_drive_path(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[0].isalpha() and value[2] in {"\\", "/"}


def _is_windows_drive_path(path: Path | PureWindowsPath) -> bool:
    return isinstance(path, PureWindowsPath) or _looks_like_windows_drive_path(str(path))


def _path_text(path: Path | PureWindowsPath) -> str:
    if _is_windows_drive_path(path):
        return str(path).replace("\\", "/")
    return str(path)


def _normalize_path_string(value: str) -> str:
    return str(value).replace("\\", "/")


def _path_name(path: Path | PureWindowsPath) -> str:
    return PureWindowsPath(str(path)).name if _is_windows_drive_path(path) else path.name


def _path_suffix(path: Path | PureWindowsPath) -> str:
    return PureWindowsPath(str(path)).suffix if _is_windows_drive_path(path) else path.suffix


def _path_exists(path: Path | PureWindowsPath) -> bool:
    if _is_windows_drive_path(path) and os.name != "nt":
        return False
    return Path(path).exists()
