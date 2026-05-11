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
DESCRIPTOR_TYPE = "asyncroscopy.tiled_dataset"


def acquisition_config(
    *,
    save_directory: str | os.PathLike[str] | None = None,
    tiled_uri: str | None = None,
    tiled_root_path: str | None = None,
    file_format: str | None = None,
) -> dict[str, str]:
    """Build a normalized Tiled acquisition config."""
    return {
        "save_directory": str(
            save_directory
            or os.environ.get("ASYNCROSCOPY_ACQUISITION_DIR")
            or DEFAULT_ACQUISITION_DIR
        ),
        "tiled_uri": tiled_uri or os.environ.get("ASYNCROSCOPY_TILED_URI") or DEFAULT_TILED_URI,
        "tiled_root_path": (tiled_root_path or os.environ.get("ASYNCROSCOPY_TILED_ROOT_PATH") or "").strip("/"),
        "file_format": (file_format or os.environ.get("ASYNCROSCOPY_ACQUISITION_FORMAT") or "tiff").lower().lstrip("."),
    }


def configure_tiled_acquisition(
    microscope_proxy: Any,
    *,
    save_directory: str | os.PathLike[str],
    tiled_uri: str | None = None,
    tiled_root_path: str | None = None,
    file_format: str = "emd",
) -> dict[str, str]:
    """Configure a ThermoMicroscope proxy for descriptor-returning acquisitions."""
    config = acquisition_config(
        save_directory=save_directory,
        tiled_uri=tiled_uri,
        tiled_root_path=tiled_root_path,
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
    parameters: dict[str, Any] | None = None,
) -> str:
    """Save an AutoScript adorned object and return a JSON Tiled descriptor."""
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

    saved_format = "tiff"
    path = _save_with_native_adorned_writer(adorned, path)

    if not _path_exists(path):
        if not (_is_windows_drive_path(path) and os.name != "nt"):
            raise FileNotFoundError(
                "Acquisition save returned without creating a file. "
                f"Expected path: {_path_text(path)}. "
                f"Save directory: {_path_text(save_directory)}. "
                f"Process working directory: {Path.cwd()}."
            )

    relative_path = _relative_or_name(path, save_directory)
    descriptor = {
        "descriptor_type": DESCRIPTOR_TYPE,
        "version": 1,
        "acquisition_type": acquisition_type,
        "detector": detector,
        "timestamp": timestamp,
        "format": saved_format,
        "path": _path_text(path),
        "file_name": _path_name(path),
        "relative_path": relative_path,
        "tiled_uri": config.get("tiled_uri") or DEFAULT_TILED_URI,
        "tiled_root_path": config.get("tiled_root_path", ""),
        "tiled_path_candidates": tiled_path_candidates(relative_path, config.get("tiled_root_path", "")),
        "parameters": parameters or {},
        "file_exists": _path_exists(path),
        "file_size_bytes": Path(path).stat().st_size if _path_exists(path) else None,
    }
    return json.dumps(descriptor)


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


def descriptor_path_candidates(descriptor: dict[str, Any]) -> list[str]:
    """Build likely Tiled paths from all path fields in a descriptor."""
    root = str(descriptor.get("tiled_root_path", "")).strip("/")
    candidates = list(descriptor.get("tiled_path_candidates", []))

    for value in [
        descriptor.get("relative_path"),
        descriptor.get("file_name"),
        descriptor.get("path"),
    ]:
        if not value:
            continue
        path = Path(str(value))
        pieces = [path.name]
        if path.suffix:
            pieces.append(path.stem)
        if not path.is_absolute():
            pieces.extend(tiled_path_candidates(str(path), root))
        else:
            parents = list(path.parents)
            for index, parent in enumerate(parents):
                try:
                    rel = path.relative_to(parent)
                except ValueError:
                    continue
                if index > 4:
                    break
                pieces.extend(tiled_path_candidates(str(rel), root))
        candidates.extend(pieces)

    return list(dict.fromkeys(candidate.strip("/") for candidate in candidates if candidate))


def connect_tiled_client(uri: str | None = None, api_key: str | None = None):
    """Connect to a Tiled server using the same API-key pattern as notebooks."""
    from tiled.client import from_uri

    uri = uri or os.environ.get("ASYNCROSCOPY_TILED_URI") or DEFAULT_TILED_URI
    api_key = api_key if api_key is not None else os.environ.get("TILED_API_KEY")
    kwargs = {"api_key": api_key} if api_key else {}
    return from_uri(uri, **kwargs)


def get_tiled_dataset(
    descriptor: str | dict[str, Any],
    *,
    client: Any | None = None,
    uri: str | None = None,
    api_key: str | None = None,
) -> Any:
    """Resolve an asyncroscopy descriptor to a node in a Tiled client."""
    info = parse_descriptor(descriptor)
    client = client or connect_tiled_client(uri or info.get("tiled_uri"), api_key=api_key)

    errors = []
    for candidate in descriptor_path_candidates(info):
        try:
            return _walk_tiled_path(client, candidate)
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")

    raise KeyError(
        "Could not resolve descriptor in Tiled. Tried: "
        + "; ".join(errors)
    )


def read_tiled_dataset(
    descriptor: str | dict[str, Any],
    *,
    client: Any | None = None,
    uri: str | None = None,
    api_key: str | None = None,
) -> Any:
    """Resolve a descriptor and read the dataset when the Tiled node supports it."""
    node = get_tiled_dataset(descriptor, client=client, uri=uri, api_key=api_key)
    if hasattr(node, "read"):
        return node.read()
    try:
        return node[:]
    except Exception:
        return node


def parse_descriptor(descriptor: str | dict[str, Any]) -> dict[str, Any]:
    """Parse and validate a descriptor returned by a microscope command."""
    info = json.loads(descriptor) if isinstance(descriptor, str) else dict(descriptor)
    if info.get("descriptor_type") != DESCRIPTOR_TYPE:
        raise ValueError(f"Not an asyncroscopy Tiled descriptor: {info.get('descriptor_type')}")
    return info


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


def _walk_tiled_path(client: Any, tiled_path: str) -> Any:
    node = client
    for part in [piece for piece in tiled_path.split("/") if piece]:
        node = node[part]
    return node


def _safe_name(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in str(value).strip().lower())
    return safe.strip("_") or "acquisition"


def _stamp(timestamp: float) -> str:
    return time.strftime("%Y%m%dT%H%M%S", time.localtime(timestamp))


def _relative_or_name(path: Path | PureWindowsPath, parent: Path | PureWindowsPath) -> str:
    if _is_windows_drive_path(path) or _is_windows_drive_path(parent):
        try:
            rel = PureWindowsPath(_path_text(path)).relative_to(PureWindowsPath(_path_text(parent)))
            return rel.as_posix()
        except ValueError:
            return _path_name(path)
    try:
        return str(path.relative_to(parent))
    except ValueError:
        return path.name


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


def _path_name(path: Path | PureWindowsPath) -> str:
    return PureWindowsPath(str(path)).name if _is_windows_drive_path(path) else path.name


def _path_suffix(path: Path | PureWindowsPath) -> str:
    return PureWindowsPath(str(path)).suffix if _is_windows_drive_path(path) else path.suffix


def _path_exists(path: Path | PureWindowsPath) -> bool:
    if _is_windows_drive_path(path) and os.name != "nt":
        return False
    return Path(path).exists()
