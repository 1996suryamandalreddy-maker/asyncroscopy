"""Helpers for saving AutoScript acquisitions and resolving them through Tiled."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
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
        "file_format": (file_format or os.environ.get("ASYNCROSCOPY_ACQUISITION_FORMAT") or "emd").lower().lstrip("."),
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
    save_directory = Path(config["save_directory"]).expanduser().resolve()
    save_directory.mkdir(parents=True, exist_ok=True)

    file_format = config.get("file_format", "emd").lower().lstrip(".")
    if file_format not in {"emd", "tiff", "tif"}:
        raise ValueError(f"Unsupported acquisition file format: {file_format}")

    suffix = ".emd" if file_format == "emd" else ".tiff"
    timestamp = time.time()
    path = save_directory / f"{_safe_name(acquisition_type)}_{_safe_name(detector)}_{_stamp(timestamp)}_{uuid.uuid4().hex[:8]}{suffix}"

    saved_format = file_format
    save_error = None
    if file_format == "emd":
        try:
            _save_as_emd(adorned, path)
        except Exception as exc:
            save_error = f"EMD save failed; fell back to TIFF: {exc}"
            saved_format = "tiff"
            path = path.with_suffix(".tiff")
            adorned.save(str(path))
    else:
        adorned.save(str(path))

    relative_path = _relative_or_name(path, save_directory)
    descriptor = {
        "descriptor_type": DESCRIPTOR_TYPE,
        "version": 1,
        "acquisition_type": acquisition_type,
        "detector": detector,
        "timestamp": timestamp,
        "format": saved_format,
        "path": str(path),
        "file_name": path.name,
        "relative_path": relative_path,
        "tiled_uri": config.get("tiled_uri") or DEFAULT_TILED_URI,
        "tiled_root_path": config.get("tiled_root_path", ""),
        "tiled_path_candidates": tiled_path_candidates(relative_path, config.get("tiled_root_path", "")),
        "parameters": parameters or {},
    }
    if save_error is not None:
        descriptor["save_warning"] = save_error
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
    for candidate in info.get("tiled_path_candidates", []):
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


def _save_as_emd(adorned: Any, path: Path) -> None:
    from autoscript_tem_microscope_client.structures import EmdFile, EmdStemFeature

    emd_file = EmdFile.create(str(path), EmdStemFeature([adorned]))
    emd_file.close()


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


def _relative_or_name(path: Path, parent: Path) -> str:
    try:
        return str(path.relative_to(parent))
    except ValueError:
        return path.name
