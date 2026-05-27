"""
Tests for the DigitalTwin Tango device.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
from pathlib import Path

import numpy as np
import pytest
import tango
from PIL import Image

class TestDigitalTwin:

    def test_state_is_on(self, twin_proxy: tango.DeviceProxy):
        assert twin_proxy.state() == tango.DevState.ON

    def test_manufacturer_is_digital_twin(self, twin_proxy: tango.DeviceProxy):
        assert twin_proxy.manufacturer == "UTKTeam"

    def test_get_image_returns_saved_tiff(self, twin_proxy: tango.DeviceProxy, scan_proxy: tango.DeviceProxy):
        scan_proxy.imsize = 32
        scan_proxy.dwell_time = 1e-6

        saved_path = Path(twin_proxy.get_scanned_image())

        assert saved_path.suffix == ".tiff"
        assert saved_path.exists()
        opened = Image.open(saved_path)
        image = np.asarray(opened)
        assert image.shape == (32, 32)
        metadata = json.loads(opened.tag_v2[270])
        assert metadata["acquisition_type"] == "stem_image"
        assert metadata["detector"] == "HAADF"

    def test_stage_navigation_changes_and_restores_view(
        self,
        twin_proxy: tango.DeviceProxy,
        scan_proxy: tango.DeviceProxy,
        monkeypatch: pytest.MonkeyPatch,
    ):
        def fake_stage_render(self, imsize: int, dwell_time: float, detector_list: list):
            self._sync_stage_from_proxy()
            stage_signal = int(round((self._stage_position[0] - self._stage_position[1]) * 1e10))
            return np.full((imsize, imsize), stage_signal, dtype=np.int16)

        from asyncroscopy.DigitalTwin import DigitalTwin

        monkeypatch.setattr(DigitalTwin, "_render_stem_image", fake_stage_render)

        scan_proxy.imsize = 64
        scan_proxy.dwell_time = 1e-6

        twin_proxy.move_stage([0.0, 0.0, 0.0, 0.0, 0.0])
        image_a = np.asarray(Image.open(twin_proxy.get_scanned_image()))

        twin_proxy.move_stage([8e-9, -7e-9, 0.0, 0.0, 0.0])
        image_b = np.asarray(Image.open(twin_proxy.get_scanned_image()))
        assert not np.array_equal(image_a, image_b)

        twin_proxy.move_stage([0.0, 0.0, 0.0, 0.0, 0.0])
        image_a_again = np.asarray(Image.open(twin_proxy.get_scanned_image()))
        assert np.array_equal(image_a, image_a_again)

    def test_spectrum_is_repeatable_at_same_pose_and_beam(
        self,
        twin_proxy: tango.DeviceProxy,
        eds_proxy: tango.DeviceProxy,
    ):
        eds_proxy.exposure_time = 0.05
        twin_proxy.move_stage([0.0, 0.0, 0.0, 0.0, 0.0])
        twin_proxy.place_beam([0.45, 0.55])

        spec_1 = np.load(twin_proxy.get_spectrum("eds"))
        spec_2 = np.load(twin_proxy.get_spectrum("eds"))
        assert spec_1.tolist() == spec_2.tolist()
