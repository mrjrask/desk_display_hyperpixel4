from pathlib import Path

import paths
import storage_overrides


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def test_config_override_controls_storage(monkeypatch, tmp_path):
    hint_path = tmp_path / "hint.txt"
    monkeypatch.setattr(paths, "_SHARED_HINT_PATH", hint_path)
    _remove_file(hint_path)

    override_dir = tmp_path / "custom_root" / "screenshots"
    monkeypatch.setattr(storage_overrides, "SCREENSHOT_DIR", str(override_dir), raising=False)
    monkeypatch.delenv("DESK_DISPLAY_SCREENSHOT_DIR", raising=False)

    storage_paths = paths.resolve_storage_paths(logger=None)

    assert storage_paths.screenshot_dir == override_dir
    assert storage_paths.archive_base == override_dir.parent / "screenshot_archive"
    assert override_dir.is_dir()
    assert (override_dir.parent / "screenshot_archive").is_dir()


def test_env_override_beats_config(monkeypatch, tmp_path):
    hint_path = tmp_path / "hint.txt"
    monkeypatch.setattr(paths, "_SHARED_HINT_PATH", hint_path)
    _remove_file(hint_path)

    config_dir = tmp_path / "from_config" / "screenshots"
    env_dir = tmp_path / "from_env" / "screenshots"

    monkeypatch.setattr(storage_overrides, "SCREENSHOT_DIR", str(config_dir), raising=False)
    monkeypatch.setenv("DESK_DISPLAY_SCREENSHOT_DIR", str(env_dir))

    storage_paths = paths.resolve_storage_paths(logger=None)

    assert storage_paths.screenshot_dir == env_dir
    assert storage_paths.archive_base == env_dir.parent / "screenshot_archive"
