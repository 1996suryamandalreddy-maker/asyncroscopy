"""
JEOL electron microscope Tango device.

This module starts from the JEOL implementation that exists on upstream/main
and adapts it to the instrument-centered package layout.
"""

from datetime import datetime
from pathlib import Path

import tango
from tango import DevState
from tango.server import device_property

from asyncroscopy.data.data_writer import DEFAULT_ACQUISITION_DIR, ReplicaAdornedImageJeol, save_acquisition
from asyncroscopy.instruments.electron_microscope.electron_microscope import ElectronMicroscope

# PyJEM imports -> this block will be removed after testing this on remote pc
try:
    from PyJEM import detector

    _PYJEM_AVAILABLE = True
except ImportError:
    _PYJEM_AVAILABLE = False


class JeolMicroscope(ElectronMicroscope):
    """
    JEOL microscope adapter.

    Detector-specific settings such as dwell time and resolution are stored in
    dedicated detector devices and read via DeviceProxy at acquisition time.
    """

    pyjem_host_ip = device_property(
        dtype=str,
        default_value='10.46.217.241',
        doc='Hostname or IP of the JEOL microscope control server.',
    )
    pyjem_host_port = device_property(
        dtype=int,
        default_value=9095,
        doc='Port of the JEOL microscope control server.',
    )
    acquisition_save_directory = device_property(
        dtype=str,
        default_value=DEFAULT_ACQUISITION_DIR,
        doc='Directory where JEOL acquisitions are saved before the Tiled server serves them.',
    )
    acquisition_file_format = device_property(
        dtype=str,
        default_value='h5',
        doc='Acquisition file format. HDF5 stores acquisition data and parsed metadata attributes.',
    )
    data_device_address = device_property(
        dtype=str,
        default_value='',
        doc="Optional Tango device address for the DATA device, e.g. 'asyncroscopy/data/default'.",
    )

    def _connect(self):
        self._connect_hardware()
        self._connect_detector_proxies()
        self.set_state(DevState.ON)

    def _connect_hardware(self) -> None:
        self._microscope = None
        self.warn_stream('JEOL/PyJEM hardware connection is not implemented yet.')

    def _connect_detector_proxies(self) -> None:
        addresses: dict[str, str] = {
            'eds': self.eds_device_address,
            'stage': self.stage_device_address,
            'scan': self.scan_device_address,
            'camera': self.camera_device_address,
            'flucam': self.flucam_device_address,
            'data': self.data_device_address,
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

    # ------------------------------------------------------------------
    # Attributes
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Attribute read methods
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Commands pertaining to setting children attributes, e.g. stage position, scan parameters, EDS settings, etc. --> iuser accesses it in a jupyter notebook using the device proxy
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Internal acquisition helpers
    # ------------------------------------------------------------------
    def _persist(self, adorned, acquisition_type, detector, data_server, dataset_name='image'):
        """Save acquired images in the format requested by the SCAN device."""
        scan = self._detector_proxies.get('scan')
        fmt = scan.output_format if scan is not None else '.h5'
        if fmt == '.h5':
            return save_acquisition(self, data_server, acquisition_type, detector, adorned, dataset_name=dataset_name)
        if fmt != '.tiff':
            raise ValueError(f"Unsupported output_format {fmt!r}; expected '.h5' or '.tiff'")

        images = list(adorned) if isinstance(adorned, (list, tuple)) else [adorned]
        detectors = list(detector) if isinstance(detector, (list, tuple)) else [detector]
        if len(images) != len(detectors):
            raise ValueError(f'Got {len(images)} images for {len(detectors)} detector(s) {detectors}')

        save_dir = data_server.save_path if data_server is not None else DEFAULT_ACQUISITION_DIR
        directory = Path(save_dir).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%dT%H%M%S%f')
        stem = f'{acquisition_type}_{stamp}'
        for img, det in zip(images, detectors):
            path = directory / f'{stem}_{det}.tiff'
            img.save(str(path))
            if data_server is not None:
                data_server.register_path(str(path))
        return stem

    def _acquire_scanned_image(
        self,
        imsize: int,
        dwell_time: float,
        detector_list: list[str] = ['haadf'],
        scan_region: list[float] = [0.0, 0.0, 1.0, 1.0],
    ) -> str:
        """
        Acquire a STEM scan over the requested detectors via the PyJEM
        ``detector`` module and return the saved acquisition's DATA/Tiled key.

        PyJEM acquisition is synchronous, so each detector is scanned in turn.
        ``dwell_time`` is given in seconds; the PyJEM API takes microseconds.
        """
        if not _PYJEM_AVAILABLE:
            tango.Except.throw_exception(
                'UnsupportedCommand',
                'PyJEM is not installed; cannot acquire on JEOL hardware.',
                '_acquire_scanned_image()',
            )

        detector_list = [d.upper() for d in detector_list]
        full_frame = [0.0, 0.0, 1.0, 1.0]
        images = []
        for name in detector_list:
            det = detector.Detector(name)
            if scan_region == full_frame:
                det.set_scanmode(0)                          # full-frame Scan
                det.set_imaging_area(imsize, imsize)
            else:
                extent = det.get_detectorsetting()['ImagingArea']['Width']
                left, top, right, bottom = scan_region
                det.set_scanmode(3)                          # Area (sub-region)
                det.set_areamode_imagingarea(
                    Width=int((right - left) * extent),
                    Height=int((bottom - top) * extent),
                    X=int(left * extent),
                    Y=int(top * extent),
                )
            det.set_exposuretime_value(dwell_time * 1e6)     # API takes microseconds
            images.append(ReplicaAdornedImageJeol(det.snapshot_rawdata(), det.get_detectorsetting()))

        data_server = self._detector_proxies.get('data')
        return self._persist(images, 'stem_image', detector_list, data_server)

    def _acquire_spectrum(self, detector_name: str, exposure_time: float) -> str:
        tango.Except.throw_exception('UnsupportedCommand', 'JEOL spectrum acquisition is not implemented yet.', '_acquire_spectrum()')

    def _set_screen_current(self, current):
        tango.Except.throw_exception('UnsupportedCommand', 'JEOL screen current control is not implemented yet.', '_set_screen_current()')

    def _get_screen_current(self):
        tango.Except.throw_exception('UnsupportedCommand', 'JEOL screen current readback is not implemented yet.', '_get_screen_current()')

    def _move_stage(self, position):
        tango.Except.throw_exception('UnsupportedCommand', 'JEOL stage motion is not implemented yet.', '_move_stage()')

    def _get_stage(self):
        tango.Except.throw_exception('UnsupportedCommand', 'JEOL stage readback is not implemented yet.', '_get_stage()')

    def _set_fov(self, fov):
        tango.Except.throw_exception('UnsupportedCommand', 'JEOL field-of-view control is not implemented yet.', '_set_fov()')

    def _get_fov(self):
        tango.Except.throw_exception('UnsupportedCommand', 'JEOL field-of-view readback is not implemented yet.', '_get_fov()')

    def _auto_focus(self):
        tango.Except.throw_exception('UnsupportedCommand', 'JEOL autofocus is not implemented yet.', '_auto_focus()')

    def _set_image_shift(self, shift):
        tango.Except.throw_exception('UnsupportedCommand', 'JEOL image shift control is not implemented yet.', '_set_image_shift()')


if __name__ == '__main__':
    JeolMicroscope.run_server()
