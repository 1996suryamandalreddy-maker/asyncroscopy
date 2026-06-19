"""Hackathon digital twin backed by pre-split 4D-STEM camera frames."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import tango
from tango.server import device_property

from asyncroscopy.instruments.electron_microscope.digital_twin import DigitalTwin

DEFAULT_HACKATHON_DATA_DIR = '/Users/austin/Desktop/18167694/hackathon_data'
DEFAULT_CAMERA_FRAME_PREFIX = 'camera_image'
DEFAULT_CAMERA_GRID_SHAPE = (512, 512)
DEFAULT_OVERVIEW_FILENAME = 'overview_haadf.h5'


class HackathonDigitalTwin(DigitalTwin):
    """Digital twin that returns deterministic Tiled keys for precomputed 4D-STEM frames."""

    hackathon_data_directory = device_property(
        dtype=str,
        default_value=DEFAULT_HACKATHON_DATA_DIR,
        doc='Directory containing the hackathon HDF5 source and derived acquisition files.',
    )
    camera_frame_prefix = device_property(
        dtype=str,
        default_value=DEFAULT_CAMERA_FRAME_PREFIX,
        doc='Prefix for deterministic 2D camera acquisition files registered with Tiled.',
    )
    overview_filename = device_property(
        dtype=str,
        default_value=DEFAULT_OVERVIEW_FILENAME,
        doc='HDF5 overview image filename registered for acquire_scanned_image.',
    )

    def _connect_detector_proxies(self) -> None:
        addresses: dict[str, str] = {
            'camera': self.camera_device_address,
            'scan': self.scan_device_address,
        }
        for name, address in addresses.items():
            if not address:
                self.info_stream(f'Skipping {name}: no address configured')
                continue
            try:
                proxy = tango.DeviceProxy(address)
                proxy.set_timeout_millis(12_000)
                self._detector_proxies[name] = proxy
                self.info_stream(f'Connected to detector proxy: {name} @ {address}')
            except tango.DevFailed as exc:
                self.error_stream(f'Failed to connect to {name} proxy at {address}: {exc}')

    def _hackathon_data_dir(self) -> Path:
        configured = str(self.hackathon_data_directory).strip()
        env_path = os.environ.get('ASYNCROSCOPY_HACKATHON_DATA_DIR', '').strip()
        path = Path(env_path or configured or DEFAULT_HACKATHON_DATA_DIR).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _beam_index(self) -> tuple[int, int]:
        beam_x, beam_y = self.read_beam_pos()
        grid_x, grid_y = DEFAULT_CAMERA_GRID_SHAPE
        ix = int(np.clip(round(float(beam_x) * (grid_x - 1)), 0, grid_x - 1))
        iy = int(np.clip(round(float(beam_y) * (grid_y - 1)), 0, grid_y - 1))
        return ix, iy

    def _camera_frame_key(self, beam_index: tuple[int, int]) -> str:
        prefix = str(self.camera_frame_prefix).strip() or DEFAULT_CAMERA_FRAME_PREFIX
        ix, iy = beam_index
        return f'{prefix}_x{ix:03d}_y{iy:03d}.h5'

    def _acquire_camera_image(self, imsize: int, exposure_time: float, detector: str, readout_area: str) -> str:
        return self._camera_frame_key(self._beam_index())

    def _overview_path(self) -> Path:
        filename = str(self.overview_filename).strip() or DEFAULT_OVERVIEW_FILENAME
        return self._hackathon_data_dir() / filename

    def _acquire_scanned_image(
        self,
        imsize: int,
        dwell_time: float,
        detector_list: list[str] = ['haadf'],
        scan_region: list[float] = [0.0, 0.0, 1.0, 1.0],
    ) -> str:
        return self._overview_path().name


if __name__ == '__main__':
    HackathonDigitalTwin.run_server()
