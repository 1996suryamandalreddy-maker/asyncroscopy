"""Simple HDF5 acquisition writer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import h5py
import numpy as np

DEFAULT_ACQUISITION_DIR = "outputs/tiled_acquisitions"


def acquisition_filename(
    acquisition_type: str,
    detector: str,
    data_server=None,
    save_directory: str | None = None,
    extension: str = "h5",
) -> Path:
    """Create a timestamped acquisition filename."""
    if save_directory is None:
        save_directory = DEFAULT_ACQUISITION_DIR
    if data_server is not None and hasattr(data_server, "save_path"):
        save_directory = data_server.save_path

    directory = Path(save_directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    return directory / f"{acquisition_type}_{detector}_{stamp}.{extension.lower().lstrip('.')}"


def device_acquisition_filename(device, acquisition_type: str, detector: str, data_server=None, extension: str = "h5") -> Path:
    """Create an acquisition filename using a Tango device's save directory when available."""
    save_directory = DEFAULT_ACQUISITION_DIR
    try:
        save_directory = device.acquisition_save_directory
    except AttributeError:
        pass
    return acquisition_filename(acquisition_type, detector, data_server, save_directory, extension)


def register_acquisition_path(path: str | Path, data_server=None) -> str:
    """Register a saved acquisition with DATA, or return the path if DATA is absent."""
    if data_server is None:
        return str(path)
    return data_server.register_path(str(path))


def save_dataset(path: str | Path, name: str, source, **attrs) -> None:
    """Save one dataset to an acquisition HDF5 file."""
    save_acquisition_hdf5(path, [{"name": name, "source": source, "attrs": attrs}])


def save_labeled_datasets(
    path: str | Path,
    group_name: str,
    sources,
    labels: list[str],
    **attrs,
) -> None:
    """Save several correlated datasets into one HDF5 group."""
    datasets = []
    for index, source in enumerate(sources):
        label = labels[index] if index < len(labels) else f"item_{index}"
        dataset_attrs = {**attrs, "detector": label}
        datasets.append({"name": f"{group_name}/{label}", "source": source, "attrs": dataset_attrs})
    save_acquisition_hdf5(path, datasets)


def save_acquisition_hdf5(path: str | Path, datasets: list[dict], file_attrs: dict | None = None) -> None:
    """Save one acquisition event to one HDF5 file."""
    with h5py.File(path, "w") as h5:
        for key, value in (file_attrs or {}).items():
            h5.attrs[key] = value if isinstance(value, (str, int, float, bool, np.number)) else json.dumps(value)

        for item in datasets:
            source = item.get("source", item.get("data"))
            data = source.data if hasattr(source, "data") and not isinstance(source, np.ndarray) else source
            name = item["name"]
            if "/" in name:
                group_name, dataset_name = name.rsplit("/", 1)
                dset = h5.require_group(group_name).create_dataset(dataset_name, data=data, compression=None)
            else:
                dset = h5.create_dataset(name, data=data, compression=None)

            for key, value in item.get("attrs", {}).items():
                dset.attrs[key] = value if isinstance(value, (str, int, float, bool, np.number)) else json.dumps(value)

            metadata = getattr(source, "metadata", None)
            metadata_xml = getattr(metadata, "metadata_as_xml", None)
            if metadata_xml:
                root = ET.fromstring(metadata_xml)
                for elem in root.iter():
                    if elem.text and elem.text.strip():
                        key = elem.tag
                        if key in dset.attrs:
                            key = f"{key}_{len(dset.attrs)}"
                        dset.attrs[key] = elem.text.strip()
