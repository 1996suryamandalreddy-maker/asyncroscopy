from pathlib import Path

from asyncroscopy.instruments.electron_microscope.hackathon_digital_twin import HackathonDigitalTwin


def twin_for_path(tmp_path: Path) -> HackathonDigitalTwin:
    twin = HackathonDigitalTwin.__new__(HackathonDigitalTwin)
    twin._tango_properties = {}
    twin._detector_proxies = {}
    twin.hackathon_data_directory = str(tmp_path)
    twin.camera_frame_prefix = 'camera_image'
    twin.overview_filename = 'overview_haadf.h5'
    return twin


def test_hackathon_digital_twin_maps_beam_position_to_camera_key(tmp_path: Path):
    twin = twin_for_path(tmp_path)
    twin._beam_pos_x = 1.0
    twin._beam_pos_y = 0.0

    assert twin._beam_index() == (511, 0)
    assert twin._camera_frame_key(twin._beam_index()) == 'camera_image_x511_y000.h5'


def test_hackathon_camera_acquisition_returns_deterministic_key(tmp_path: Path):
    twin = twin_for_path(tmp_path)
    twin._beam_pos_x = 1.0
    twin._beam_pos_y = 0.0

    key = twin._acquire_camera_image(192, 0.1, 'BM-Ceta', 'Full')

    assert key == 'camera_image_x511_y000.h5'


def test_hackathon_scanned_image_returns_overview_key(tmp_path: Path):
    twin = twin_for_path(tmp_path)

    key = twin._acquire_scanned_image(512, 1e-6, ['haadf'])

    assert key == 'overview_haadf.h5'
