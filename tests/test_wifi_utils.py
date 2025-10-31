from services import wifi_utils


class DummyResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_check_internet_falls_back_without_interface_binding(monkeypatch):
    calls = []

    def fake_run(args, capture_output=True, text=True, check=False):
        calls.append(tuple(args))
        if "-I" in args:
            return DummyResult(returncode=2, stderr="ping: connect: Operation not permitted")
        return DummyResult(returncode=0)

    monkeypatch.setattr(wifi_utils, "_run_command", fake_run)
    monkeypatch.setattr(wifi_utils, "PING_HOSTS", ("8.8.8.8",))

    ok, tried = wifi_utils._check_internet("wlan0")

    assert ok is True
    assert tried == ["8.8.8.8"]
    assert len(calls) == 2
    assert "-I" in calls[0]
    assert all("-I" not in arg for arg in calls[1])


def test_start_monitor_defaults_to_ok_when_no_interface(monkeypatch):
    monkeypatch.setattr(wifi_utils, "_detect_interface", lambda: None)

    recorded = []

    def fake_update(state, ssid):
        recorded.append((state, ssid))
        wifi_utils.wifi_status = state
        wifi_utils.current_ssid = ssid

    monkeypatch.setattr(wifi_utils, "_update_state", fake_update)

    wifi_utils.wifi_status = "no_wifi"
    wifi_utils.current_ssid = None

    wifi_utils.start_monitor()

    assert wifi_utils.wifi_status == "ok"
    assert recorded == [("ok", None)]


def test_monitor_uses_fallback_ssid_when_link_info_missing(monkeypatch):
    class _Stopper:
        def __init__(self):
            self.calls = 0

        def is_set(self):
            return self.calls > 0

        def wait(self, seconds):
            self.calls += 1
            return True

    monkeypatch.setattr(wifi_utils, "_STOP_EVENT", _Stopper())
    monkeypatch.setattr(wifi_utils, "_get_link_info", lambda iface: "")
    monkeypatch.setattr(wifi_utils, "_get_ssid_from_link", lambda info: None)
    monkeypatch.setattr(wifi_utils, "_get_ssid_fallback", lambda: "HomeWiFi")
    monkeypatch.setattr(wifi_utils, "_has_default_route", lambda iface: True)
    monkeypatch.setattr(wifi_utils, "_check_internet", lambda iface: (True, []))
    monkeypatch.setattr(wifi_utils, "_sleep_with_stop", lambda seconds: True)
    monkeypatch.setattr(wifi_utils, "_report_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(wifi_utils, "_disable_powersave", lambda iface: None)
    monkeypatch.setattr(wifi_utils, "_system_log", lambda *args, **kwargs: None)

    monkeypatch.setattr(wifi_utils, "_IFACE", "wlan0", raising=False)
    wifi_utils.wifi_status = "no_wifi"
    wifi_utils.current_ssid = None

    wifi_utils._monitor_loop()

    assert wifi_utils.wifi_status == "ok"
    assert wifi_utils.current_ssid == "HomeWiFi"
