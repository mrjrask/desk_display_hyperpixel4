#!/usr/bin/env python3
"""Minimal admin service that surfaces the latest screenshots per screen."""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request

from schedule import build_scheduler
from paths import resolve_storage_paths
from screen_overrides import load_overrides as load_screen_overrides, save_overrides as save_screen_overrides

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "screens_config.json")
OVERRIDES_PATH = os.path.join(SCRIPT_DIR, "screen_overrides.json")

_logger = logging.getLogger(__name__)
_storage_paths = resolve_storage_paths(logger=_logger)
SCREENSHOT_DIR = str(_storage_paths.screenshot_dir)
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}

DEVICE_PROFILE_CHOICES = [
    ("hyperpixel4_square", "HyperPixel 4.0 Square (720×720)"),
    ("hyperpixel4_square_portrait", "HyperPixel 4.0 Square – Portrait"),
    ("hyperpixel4", "HyperPixel 4.0 Landscape (800×480)"),
    ("hyperpixel4_portrait", "HyperPixel 4.0 Portrait (480×800)"),
]
_DEVICE_PROFILE_IDS = {choice[0] for choice in DEVICE_PROFILE_CHOICES}

app = Flask(
    __name__,
    static_folder=str(_storage_paths.screenshot_dir),
    static_url_path="/screenshots",
)
_auto_render_lock = threading.Lock()
_auto_render_done = False


@dataclass
class ScreenInfo:
    id: str
    frequency: int
    last_screenshot: Optional[str]
    last_captured: Optional[str]
    overrides: Dict[str, Any] = field(default_factory=dict)


def _sanitize_directory_name(name: str) -> str:
    safe = name.strip().replace("/", "-").replace("\\", "-")
    safe = "".join(ch for ch in safe if ch.isalnum() or ch in (" ", "-", "_"))
    return safe or "Screens"


def _latest_screenshot(screen_id: str) -> Optional[tuple[str, datetime]]:
    folder = os.path.join(SCREENSHOT_DIR, _sanitize_directory_name(screen_id))
    if not os.path.isdir(folder):
        return None

    latest_path: Optional[str] = None
    latest_mtime: float = -1.0

    for entry in os.scandir(folder):
        if not entry.is_file():
            continue
        _, ext = os.path.splitext(entry.name)
        if ext.lower() not in ALLOWED_EXTENSIONS:
            continue
        mtime = entry.stat().st_mtime
        if mtime > latest_mtime:
            latest_mtime = mtime
            rel_path = os.path.join(os.path.basename(folder), entry.name)
            latest_path = rel_path.replace(os.sep, "/")

    if latest_path is None:
        return None

    captured = datetime.fromtimestamp(latest_mtime)
    return latest_path, captured


def _load_config() -> Dict[str, Dict[str, int]]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {"screens": {}}

    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object")
    screens = data.get("screens")
    if not isinstance(screens, dict):
        raise ValueError("Configuration must contain a 'screens' mapping")
    return {"screens": screens}


def _load_overrides() -> Dict[str, Dict[str, Dict[str, Any]]]:
    return load_screen_overrides(OVERRIDES_PATH)


def _save_overrides(overrides: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    save_screen_overrides(overrides, OVERRIDES_PATH)


def _normalise_optional_float(
    value: Any,
    *,
    field_name: str,
    minimum: float,
    maximum: float,
) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if number < minimum or number > maximum:
        raise ValueError(
            f"{field_name} must be between {minimum:g} and {maximum:g}"
        )
    return round(number, 4)


def _normalise_device_profile(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate not in _DEVICE_PROFILE_IDS:
            raise ValueError("Unknown device profile override")
        return candidate
    raise ValueError("Device profile override must be a string or null")


def _empty_override_entry() -> Dict[str, Dict[str, Any]]:
    return {"defaults": {}, "profiles": {}}


def _normalise_override_entry(entry: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    defaults = dict((entry or {}).get("defaults") or {})
    profiles = {
        profile: dict(values)
        for profile, values in ((entry or {}).get("profiles") or {}).items()
        if isinstance(profile, str) and isinstance(values, dict)
    }
    return {"defaults": defaults, "profiles": profiles}


def _apply_numeric_fields(target: Dict[str, Any], payload: Dict[str, Any]) -> None:
    for field_name, params in (
        ("font_scale", {"minimum": 0.25, "maximum": 5.0}),
        ("image_scale", {"minimum": 0.25, "maximum": 3.0}),
    ):
        if field_name not in payload:
            continue
        value = _normalise_optional_float(
            payload[field_name],
            field_name="Font scale" if field_name == "font_scale" else "Image scale",
            minimum=params["minimum"],
            maximum=params["maximum"],
        )
        if value is None:
            target.pop(field_name, None)
        else:
            target[field_name] = value


def _apply_device_profile(target: Dict[str, Any], payload: Dict[str, Any]) -> None:
    if "device_profile" not in payload:
        return
    profile = _normalise_device_profile(payload["device_profile"])
    if profile is None:
        target.pop("device_profile", None)
    else:
        target["device_profile"] = profile


def _merge_override_updates(
    updates: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    current = {
        screen_id: _normalise_override_entry(entry)
        for screen_id, entry in _load_overrides().items()
    }

    for screen_id, raw in updates.items():
        if not isinstance(screen_id, str):
            raise ValueError("Screen identifiers must be strings")
        if not isinstance(raw, dict):
            raise ValueError("Override values must be objects")

        entry = current.setdefault(screen_id, _empty_override_entry())
        defaults = entry.setdefault("defaults", {})
        profiles = entry.setdefault("profiles", {})

        inline_fields = {
            key: raw[key]
            for key in ("font_scale", "image_scale", "device_profile")
            if key in raw
        }
        if inline_fields:
            _apply_numeric_fields(defaults, inline_fields)
            _apply_device_profile(defaults, inline_fields)

        if "defaults" in raw:
            block = raw["defaults"]
            if block is None:
                defaults.clear()
            elif isinstance(block, dict):
                _apply_numeric_fields(defaults, block)
                _apply_device_profile(defaults, block)
            else:
                raise ValueError("Defaults override must be an object or null")

        profile_payloads = raw.get("profiles")
        if profile_payloads is not None:
            if not isinstance(profile_payloads, dict):
                raise ValueError("Profile overrides must be provided as an object")
            for profile_name, profile_block in profile_payloads.items():
                if not isinstance(profile_name, str):
                    raise ValueError("Profile names must be strings")
                if profile_block is None:
                    profiles.pop(profile_name, None)
                    continue
                if not isinstance(profile_block, dict):
                    raise ValueError("Profile overrides must be objects or null")
                target = profiles.setdefault(profile_name, {})
                _apply_numeric_fields(target, profile_block)
                _apply_device_profile(target, profile_block)
                if not target:
                    profiles.pop(profile_name, None)

        if not defaults:
            entry.pop("defaults", None)
        if not profiles:
            entry.pop("profiles", None)
        if not entry:
            current.pop(screen_id, None)

    return current


def _collect_screen_info(
    *, overrides: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None
) -> List[ScreenInfo]:
    config = _load_config()
    # Validate the configuration by attempting to build a scheduler.
    build_scheduler(config)

    overrides = overrides or _load_overrides()

    screens: List[ScreenInfo] = []
    for screen_id, freq in config["screens"].items():
        try:
            frequency = int(freq)
        except (TypeError, ValueError):
            frequency = 0
        latest = _latest_screenshot(screen_id)
        screen_overrides = _normalise_override_entry(overrides.get(screen_id))
        if latest is None:
            screens.append(
                ScreenInfo(screen_id, frequency, None, None, screen_overrides)
            )
        else:
            rel_path, captured = latest
            screens.append(
                ScreenInfo(
                    screen_id,
                    frequency,
                    rel_path,
                    captured.isoformat(timespec="seconds"),
                    screen_overrides,
                )
            )
    return screens


def _run_startup_renderer() -> None:
    """Render the latest screenshots when the service starts."""

    if app.config.get("TESTING"):
        return

    if os.environ.get("ADMIN_DISABLE_AUTO_RENDER") == "1":
        _logger.info("Skipping automatic screen render due to environment override.")
        return

    try:
        from render_all_screens import render_all_screens as _render_all_screens
    except Exception as exc:  # pragma: no cover - import errors are unexpected
        _logger.warning("Initial render unavailable: %s", exc)
        return

    try:
        _logger.info("Rendering all screens to refresh admin gallery…")
        result = _render_all_screens(sync_screenshots=True, create_archive=False)
        if result != 0:
            _logger.warning("Initial render exited with status %s", result)
    except Exception as exc:  # pragma: no cover - runtime failure is logged
        _logger.exception("Initial render failed: %s", exc)


@app.before_request
def _prime_screenshots() -> None:
    global _auto_render_done

    if _auto_render_done:
        return

    with _auto_render_lock:
        if _auto_render_done:
            return
        _run_startup_renderer()
        _auto_render_done = True


@app.route("/")
def index() -> str:
    overrides = _load_overrides()
    try:
        screens = _collect_screen_info(overrides=overrides)
        error = None
    except ValueError as exc:
        screens = []
        error = str(exc)
    return render_template(
        "admin.html",
        screens=screens,
        error=error,
        overrides=overrides,
        device_profiles=DEVICE_PROFILE_CHOICES,
    )


@app.route("/api/screens")
def api_screens():
    try:
        screens = _collect_screen_info()
        return jsonify(status="ok", screens=[screen.__dict__ for screen in screens])
    except ValueError as exc:
        return jsonify(status="error", message=str(exc)), 500


@app.route("/api/config")
def api_config():
    try:
        config = _load_config()
        return jsonify(status="ok", config=config)
    except ValueError as exc:
        return jsonify(status="error", message=str(exc)), 500


@app.route("/api/overrides", methods=["GET", "POST"])
def api_overrides():
    if request.method == "GET":
        return jsonify(status="ok", overrides=_load_overrides())

    try:
        payload = request.get_json(force=True)
    except Exception:
        payload = None

    if not isinstance(payload, dict):
        return (
            jsonify(status="error", message="Payload must be a JSON object"),
            400,
        )

    screens = payload.get("screens")
    if not isinstance(screens, dict):
        return (
            jsonify(status="error", message="Payload must contain a 'screens' object"),
            400,
        )

    try:
        merged = _merge_override_updates(screens)
    except ValueError as exc:
        return jsonify(status="error", message=str(exc)), 400

    _save_overrides(merged)
    return jsonify(status="ok", overrides=merged)


if __name__ == "__main__":  # pragma: no cover
    host = os.environ.get("ADMIN_HOST", "0.0.0.0")
    port = int(os.environ.get("ADMIN_PORT", "5001"))
    debug = os.environ.get("ADMIN_DEBUG") == "1" or os.environ.get("FLASK_DEBUG") == "1"

    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        from waitress import serve

        serve(app, host=host, port=port)
