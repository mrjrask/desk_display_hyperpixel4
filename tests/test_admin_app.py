import json
import os
import sys
from pathlib import Path

import pytest

import admin


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    config_path = tmp_path / "screens_config.json"
    config_path.write_text(json.dumps({"screens": {"date": 0, "travel": 2}}))

    screenshot_dir = tmp_path / "screenshots"
    screenshot_dir.mkdir()

    overrides_path = tmp_path / "screen_overrides.json"

    monkeypatch.setattr(admin, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(admin, "SCREENSHOT_DIR", str(screenshot_dir))
    monkeypatch.setattr(admin, "OVERRIDES_PATH", str(overrides_path))
    admin.app.static_folder = str(screenshot_dir)

    admin.app.config.update(TESTING=True)
    with admin.app.test_client() as client:
        yield client, screenshot_dir, config_path, overrides_path


def test_index_lists_screens(app_client):
    client, screenshot_dir, _, _ = app_client

    folder = screenshot_dir / admin._sanitize_directory_name("date")
    folder.mkdir()
    (folder / "date_1.png").write_bytes(b"fake")

    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "date" in body
    assert "travel" in body
    assert "Font scale multiplier" in body


def test_api_screens_reports_latest_file(app_client):
    client, screenshot_dir, _, overrides_path = app_client

    folder = screenshot_dir / admin._sanitize_directory_name("date")
    folder.mkdir(exist_ok=True)
    first = folder / "date_1.png"
    second = folder / "date_2.png"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    os.utime(first, (1, 1))
    os.utime(second, (2, 2))

    overrides_path.write_text(
        json.dumps({"screens": {"travel": {"defaults": {"font_scale": 1.5}}}})
    )

    resp = client.get("/api/screens")
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["status"] == "ok"

    screens = {entry["id"]: entry for entry in payload["screens"]}
    assert screens["date"]["last_screenshot"].endswith("date_2.png")
    assert screens["travel"]["last_screenshot"] is None
    assert screens["travel"]["overrides"]["defaults"]["font_scale"] == 1.5


def test_api_config_returns_current_config(app_client):
    client, _, config_path, _ = app_client
    resp = client.get("/api/config")
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["status"] == "ok"
    assert payload["config"]["screens"]["travel"] == 2
    assert json.loads(Path(config_path).read_text())["screens"]["date"] == 0


def test_api_overrides_round_trip(app_client):
    client, _, _, overrides_path = app_client
    resp = client.post(
        "/api/overrides",
        json={
            "screens": {
                "date": {
                    "defaults": {
                        "font_scale": 1.5,
                        "image_scale": 0.9,
                        "device_profile": "hyperpixel4",
                    },
                    "profiles": {
                        "hyperpixel4_square": {
                            "font_scale": 1.2,
                        }
                    },
                }
            }
        },
    )
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["status"] == "ok"
    assert payload["overrides"]["date"]["defaults"]["device_profile"] == "hyperpixel4"
    assert (
        payload["overrides"]["date"]["profiles"]["hyperpixel4_square"]["font_scale"]
        == 1.2
    )
    on_disk = json.loads(overrides_path.read_text())
    assert on_disk["screens"]["date"]["defaults"]["font_scale"] == 1.5


def test_api_overrides_rejects_invalid_payload(app_client):
    client, _, _, overrides_path = app_client
    resp = client.post(
        "/api/overrides",
        json={"screens": {"travel": {"defaults": {"font_scale": 0.1}}}},
    )
    assert resp.status_code == 400
    assert not overrides_path.exists()


def test_api_overrides_get_returns_current_file(app_client):
    client, _, _, overrides_path = app_client
    overrides_path.write_text(
        json.dumps(
            {
                "screens": {
                    "travel": {
                        "profiles": {"hyperpixel4": {"image_scale": 1.2}}
                    }
                }
            }
        )
    )

    resp = client.get("/api/overrides")
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["overrides"]["travel"]["profiles"]["hyperpixel4"]["image_scale"] == 1.2


def test_startup_renderer_runs_when_enabled(monkeypatch):
    calls: list[tuple[bool, bool]] = []

    class FakeRenderer:
        @staticmethod
        def render_all_screens(*, sync_screenshots=False, create_archive=True):
            calls.append((sync_screenshots, create_archive))
            return 0

    monkeypatch.setitem(sys.modules, "render_all_screens", FakeRenderer)

    previous = admin.app.config.get("TESTING")
    admin.app.config["TESTING"] = False
    try:
        admin._run_startup_renderer()
    finally:
        if previous is None:
            del admin.app.config["TESTING"]
        else:
            admin.app.config["TESTING"] = previous

    assert calls == [(True, False)]
