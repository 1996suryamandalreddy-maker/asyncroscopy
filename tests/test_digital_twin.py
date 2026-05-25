"""
Tests for the ThermoDigitalTwin Tango device.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import numpy as np
import pytest
import tango

# Using shared twin_proxy from conftest.py

class FakeAdornedImage:
    def __init__(self, data: np.ndarray):
        self.data = data


class TestThermoDigitalTwin:

    def test_state_is_on(self, twin_proxy: tango.DeviceProxy):
        assert twin_proxy.state() == tango.DevState.ON

    def test_manufacturer_is_digital_twin(self, twin_proxy: tango.DeviceProxy):
        assert twin_proxy.manufacturer == "UTKTeam"

    def test_get_image_returns_valid_data(self, twin_proxy: tango.DeviceProxy, patched_single_image: pytest.MonkeyPatch):
        json_meta = twin_proxy.get_scanned_image()
        meta = json.loads(json_meta)
        
        assert meta["detector"] == "haadf"
        assert "shape" in meta
        assert "dtype" in meta
        assert meta["cache_index"] == 0
        
        _cached_meta, raw_bytes = twin_proxy.get_image_data_cached(meta["cache_index"])
        image = np.frombuffer(raw_bytes, dtype=meta["dtype"]).reshape(meta["shape"])
        assert image.shape == tuple(meta["shape"])

    def test_stage_navigation_changes_and_restores_view(
        self,
        twin_proxy: tango.DeviceProxy,
        scan_proxy: tango.DeviceProxy,
        monkeypatch: pytest.MonkeyPatch,
    ):
        def fake_stage_acquire(self, imsize: int, dwell_time: float, detector_list: list):
            self._sync_stage_from_proxy()
            stage_signal = int(round((self._stage_position[0] - self._stage_position[1]) * 1e10))
            image = np.full((imsize, imsize), stage_signal, dtype=np.int16)
            return FakeAdornedImage(image)

        from asyncroscopy.ThermoDigitalTwin import ThermoDigitalTwin

        monkeypatch.setattr(ThermoDigitalTwin, "_acquire_stem_image", fake_stage_acquire)

        scan_proxy.imsize = 64
        scan_proxy.dwell_time = 1e-6

        twin_proxy.move_stage([0.0, 0.0, 0.0, 0.0, 0.0])
        meta_a = json.loads(twin_proxy.get_scanned_image())
        _, raw_a = twin_proxy.get_image_data_cached(meta_a["cache_index"])

        twin_proxy.move_stage([8e-9, -7e-9, 0.0, 0.0, 0.0])
        meta_b = json.loads(twin_proxy.get_scanned_image())
        _, raw_b = twin_proxy.get_image_data_cached(meta_b["cache_index"])
        assert raw_a != raw_b

        twin_proxy.move_stage([0.0, 0.0, 0.0, 0.0, 0.0])
        meta_a_again = json.loads(twin_proxy.get_scanned_image())
        _, raw_a_again = twin_proxy.get_image_data_cached(meta_a_again["cache_index"])
        assert raw_a == raw_a_again

    def test_spectrum_is_repeatable_at_same_pose_and_beam(
        self,
        twin_proxy: tango.DeviceProxy,
        eds_proxy: tango.DeviceProxy,
    ):
        eds_proxy.exposure_time = 0.05
        twin_proxy.move_stage([0.0, 0.0, 0.0, 0.0, 0.0])
        twin_proxy.place_beam([0.45, 0.55])

        spec_1 = json.loads(twin_proxy.get_spectrum("eds"))
        spec_2 = json.loads(twin_proxy.get_spectrum("eds"))
        assert spec_1 == spec_2
