import json

import tango

from asyncroscopy.software.DATA import DATA


class TestDataDevice:
    def test_state_is_on(self, data_proxy: tango.DeviceProxy) -> None:
        assert data_proxy.state() == tango.DevState.ON

    def test_config_round_trip(self, data_proxy: tango.DeviceProxy, tmp_path) -> None:
        config = {
            "host": "127.0.0.1",
            "port": 9091,
            "save_path": str(tmp_path),
            "root_path": "served",
        }

        returned = json.loads(data_proxy.configure(json.dumps(config)))

        assert returned["host"] == config["host"]
        assert returned["port"] == config["port"]
        assert returned["save_path"] == config["save_path"]
        assert returned["root_path"] == config["root_path"]
        assert returned["uri"] == "http://127.0.0.1:9091"

    def test_start_tiled_server_uses_catalog_server_command(
        self,
        data_proxy: tango.DeviceProxy,
        monkeypatch,
        tmp_path,
    ) -> None:
        calls = []
        commands = []
        run_commands = []

        def fake_alive(self):
            calls.append(None)
            return len(calls) > 1

        class FakeStdout:
            def read(self):
                return ""

        class FakeProcess:
            stdout = FakeStdout()

            def poll(self):
                return None

        data_proxy.host = "127.0.0.1"
        data_proxy.port = 9091
        data_proxy.save_path = str(tmp_path)
        data_proxy.root_path = "served"
        data_proxy.set_api_key("secret")
        monkeypatch.setattr(DATA, "_tiled_alive", fake_alive)
        monkeypatch.setattr(DATA, "_tiled_executable", lambda self: "tiled")
        monkeypatch.setattr("asyncroscopy.software.DATA.subprocess.Popen", lambda command, **_: commands.append(command) or FakeProcess())
        monkeypatch.setattr(
            "asyncroscopy.software.DATA.subprocess.run",
            lambda command, **_: run_commands.append(command) or type("Result", (), {"returncode": 0, "stdout": ""})(),
        )

        returned = json.loads(data_proxy.start_tiled_server())

        assert returned["tiled_server"] == "yes"
        assert commands == [
            [
                "tiled",
                "serve",
                "catalog",
                str(tmp_path / ".asyncroscopy_tiled_catalog.db"),
                "--read",
                str(tmp_path),
                "--public",
                "--api-key",
                "secret",
                "--host",
                "127.0.0.1",
                "--port",
                "9091",
            ],
            [
                "tiled",
                "register",
                "http://127.0.0.1:9091",
                str(tmp_path),
                "--api-key",
                "secret",
                "--keep-ext",
                "--watch",
                "--prefix",
                "served",
            ],
        ]
        assert run_commands == [
            ["tiled", "catalog", "init", "--if-not-exists", str(tmp_path / ".asyncroscopy_tiled_catalog.db")],
        ]

    def test_path_exists_and_recent_files_use_save_path(self, data_proxy: tango.DeviceProxy, tmp_path) -> None:
        saved = tmp_path / "frame.tiff"
        saved.write_bytes(b"fake-tiff")
        data_proxy.save_path = str(tmp_path)

        absolute = json.loads(data_proxy.path_exists(str(saved)))
        relative = json.loads(data_proxy.path_exists(saved.name))
        recent = json.loads(data_proxy.get_recent())

        assert absolute["exists"] is True
        assert absolute["is_file"] is True
        assert absolute["size_bytes"] == len(b"fake-tiff")
        assert relative["exists"] is True
        assert recent["files"][0]["file_name"] == saved.name

    def test_register_path_registers_single_file(
        self,
        data_proxy: tango.DeviceProxy,
        monkeypatch,
        tmp_path,
    ) -> None:
        run_commands = []
        saved = tmp_path / "frame.tiff"
        saved.write_bytes(b"fake-tiff")
        data_proxy.host = "127.0.0.1"
        data_proxy.port = 9091
        data_proxy.root_path = "served"
        data_proxy.set_api_key("secret")
        monkeypatch.setattr(DATA, "_tiled_executable", lambda self: "tiled")
        monkeypatch.setattr(
            "asyncroscopy.software.DATA.subprocess.run",
            lambda command, **_: run_commands.append(command) or type("Result", (), {"returncode": 0, "stdout": "ok"})(),
        )

        result = json.loads(data_proxy.register_path(str(saved)))

        assert result["registered"] is True
        assert run_commands == [
            [
                "tiled",
                "register",
                "http://127.0.0.1:9091",
                str(saved),
                "--api-key",
                "secret",
                "--keep-ext",
                "--prefix",
                "served",
            ]
        ]
