import json

from scripts import run_servers


class FakeDataProxy:
    def __init__(self):
        self.timeout_millis = None
        self.start_called = False
        self.stop_called = False

    def set_timeout_millis(self, timeout_millis):
        self.timeout_millis = timeout_millis

    def start_tiled_server(self):
        self.start_called = True
        return json.dumps({"tiled_server": "yes", "tiled_server_status": "running"})

    def stop_tiled_server(self):
        self.stop_called = True


def test_start_tiled_server_uses_extended_data_proxy_timeout(monkeypatch):
    proxy = FakeDataProxy()
    monkeypatch.setattr(run_servers.tango, "DeviceProxy", lambda _: proxy)

    assert run_servers.start_tiled_server()["tiled_server"] == "yes"
    assert proxy.timeout_millis == run_servers.TILED_COMMAND_TIMEOUT_MILLIS
    assert proxy.start_called is True


def test_stop_tiled_server_uses_extended_data_proxy_timeout(monkeypatch):
    proxy = FakeDataProxy()
    monkeypatch.setattr(run_servers.tango, "DeviceProxy", lambda _: proxy)

    run_servers.stop_tiled_server()

    assert proxy.timeout_millis == run_servers.TILED_COMMAND_TIMEOUT_MILLIS
    assert proxy.stop_called is True
