import json

import numpy as np
import tango

from asyncroscopy.Tiled import Tiled


class FakeTiledNode:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


class FakeTiledClient(dict):
    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError as exc:
            raise KeyError(key) from exc


class TestTiledDevice:
    def test_state_is_on(self, tiled_proxy: tango.DeviceProxy) -> None:
        assert tiled_proxy.state() == tango.DevState.ON

    def test_config_round_trip(self, tiled_proxy: tango.DeviceProxy, tmp_path) -> None:
        config = {
            "host": "127.0.0.1",
            "port": 9091,
            "save_path": str(tmp_path),
            "root_path": "served",
        }

        returned = json.loads(tiled_proxy.configure(json.dumps(config)))

        assert returned["host"] == config["host"]
        assert returned["port"] == config["port"]
        assert returned["save_path"] == config["save_path"]
        assert returned["root_path"] == config["root_path"]
        assert returned["uri"] == "http://127.0.0.1:9091"

    def test_path_exists_and_recent_files_use_save_path(self, tiled_proxy: tango.DeviceProxy, tmp_path) -> None:
        saved = tmp_path / "frame.tiff"
        saved.write_bytes(b"fake-tiff")
        tiled_proxy.save_path = str(tmp_path)

        absolute = json.loads(tiled_proxy.path_exists(str(saved)))
        relative = json.loads(tiled_proxy.path_exists(saved.name))
        recent = json.loads(tiled_proxy.get_recent())

        assert absolute["exists"] is True
        assert absolute["is_file"] is True
        assert absolute["size_bytes"] == len(b"fake-tiff")
        assert relative["exists"] is True
        assert recent["files"][0]["file_name"] == saved.name

    def test_get_data_resolves_saved_path_through_tiled_client(
        self,
        tiled_proxy: tango.DeviceProxy,
        monkeypatch,
        tmp_path,
    ) -> None:
        saved = tmp_path / "frame.tiff"
        saved.write_bytes(b"fake-tiff")
        tiled_proxy.save_path = str(tmp_path)
        tiled_proxy.root_path = ""

        fake_client = FakeTiledClient(
            {
                "frame": FakeTiledNode(np.array([[1, 2], [3, 4]], dtype=np.uint8)),
            }
        )
        monkeypatch.setattr(Tiled, "_client", lambda self: fake_client)

        payload = json.loads(tiled_proxy.get_data(str(saved)))

        assert payload == {
            "type": "ndarray",
            "dtype": "uint8",
            "shape": [2, 2],
            "data": [[1, 2], [3, 4]],
        }
