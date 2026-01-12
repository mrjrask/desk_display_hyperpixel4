import json
from pathlib import Path

import pytest

import admin


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    config_path = tmp_path / "screens_config.json"
    config_path.write_text(json.dumps({"screens": {"date": 0, "travel": 2}}))
    local_config_path = tmp_path / "screens_config.local.json"

    monkeypatch.setenv("SCREENS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("SCREENS_CONFIG_LOCAL_PATH", str(local_config_path))
    monkeypatch.setattr(admin, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(admin, "CONFIG_LOCAL_PATH", str(local_config_path))

    admin.app.config.update(TESTING=True)
    with admin.app.test_client() as client:
        yield client, config_path, local_config_path


def test_index_loads_config_ui(app_client):
    client, _, _ = app_client
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Screen configuration" in body
    assert "Playlist editor" in body


def test_api_screens_reports_config_list(app_client):
    client, _, _ = app_client

    resp = client.get("/api/screens")
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["status"] == "ok"

    screens = payload["screens"]
    assert screens[0]["id"] == "date"
    assert screens[0]["frequency"] == 0
    assert screens[0]["alt_screen"] == ""
    assert screens[0]["alt_frequency"] == ""
    assert any(entry["id"] == "travel" for entry in screens)
    assert "date" in payload["screen_ids"]


def test_api_defaults_returns_defaults(app_client):
    client, _, _ = app_client
    resp = client.get("/api/screens/defaults")
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["status"] == "ok"
    assert any(entry["id"] == "travel" for entry in payload["screens"])


def test_api_screens_updates_local_override(app_client):
    client, _, local_path = app_client
    payload = {
        "screens": [
            {"id": "date", "frequency": "1", "alt_screen": "", "alt_frequency": ""},
            {"id": "travel", "frequency": "2", "alt_screen": "", "alt_frequency": ""},
        ]
    }
    resp = client.post("/api/screens", json=payload)
    assert resp.status_code == 200
    assert local_path.exists()
    on_disk = json.loads(Path(local_path).read_text())
    assert on_disk["screens"]["date"] == 1
