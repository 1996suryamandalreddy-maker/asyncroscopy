from scripts import run_servers


class FakeDataProxy:
    def __init__(self):
        self.timeout_millis = None
        self.stop_called = False

    def set_timeout_millis(self, timeout_millis):
        self.timeout_millis = timeout_millis

    def stop_tiled_server(self):
        self.stop_called = True


def test_get_data_proxy_sets_extended_timeout(monkeypatch):
    proxy = FakeDataProxy()
    monkeypatch.setattr(run_servers.tango, "DeviceProxy", lambda _: proxy)

    assert run_servers.get_data_proxy() is proxy
    assert proxy.timeout_millis == run_servers.TILED_COMMAND_TIMEOUT_MILLIS


def test_stop_tiled_server_uses_extended_data_proxy_timeout(monkeypatch):
    proxy = FakeDataProxy()
    monkeypatch.setattr(run_servers.tango, "DeviceProxy", lambda _: proxy)

    run_servers.stop_tiled_server()

    assert proxy.timeout_millis == run_servers.TILED_COMMAND_TIMEOUT_MILLIS
    assert proxy.stop_called is True
