#!/usr/bin/env python3
"""Admin service for managing screen configuration."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from flask import Flask, Response, jsonify, render_template, request

from screen_config import (
    config_to_ui_groups,
    load_active_config,
    load_default_config,
    resolve_config_paths,
    ui_to_config,
    write_config,
)
from screens_catalog import SCREEN_IDS

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH, CONFIG_LOCAL_PATH = resolve_config_paths()
CONFIG_PATH = str(CONFIG_PATH)
CONFIG_LOCAL_PATH = str(CONFIG_LOCAL_PATH)


app = Flask(__name__)


def _load_screen_config_payload(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "groups": config_to_ui_groups(config),
        "screen_ids": list(SCREEN_IDS),
    }


def _export_config_payload(config: Dict[str, Any]) -> Response:
    payload = json.dumps(config, indent=2)
    response = Response(payload, mimetype="application/json")
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=screens_config.export.json"
    return response


@app.route("/")
def index() -> str:
    return render_template("admin.html")


@app.route("/api/screens")
def api_screens():
    try:
        config = load_active_config(allow_missing=True)
        payload = _load_screen_config_payload(config)
        return jsonify(status="ok", **payload)
    except ValueError as exc:
        return jsonify(status="error", message=str(exc)), 500


@app.route("/api/screens", methods=["POST"])
def api_screens_update():
    try:
        payload = request.get_json(force=True)
    except Exception:
        payload = None

    if not isinstance(payload, dict):
        return jsonify(status="error", message="Payload must be a JSON object"), 400

    try:
        config = ui_to_config(payload)
    except ValueError as exc:
        return jsonify(status="error", message=str(exc)), 400

    write_config(Path(CONFIG_LOCAL_PATH), config)
    return jsonify(status="ok")


@app.route("/api/screens/defaults")
def api_screens_defaults():
    try:
        config = load_default_config(allow_missing=True)
        payload = _load_screen_config_payload(config)
        return jsonify(status="ok", **payload)
    except ValueError as exc:
        return jsonify(status="error", message=str(exc)), 500


@app.route("/api/screens/export")
def api_screens_export():
    try:
        config = load_active_config(allow_missing=True)
        return _export_config_payload(config)
    except ValueError as exc:
        return jsonify(status="error", message=str(exc)), 500


if __name__ == "__main__":  # pragma: no cover
    host = os.environ.get("SCREEN_CONFIG_HOST") or os.environ.get("ADMIN_HOST", "0.0.0.0")
    port = int(os.environ.get("SCREEN_CONFIG_PORT") or os.environ.get("ADMIN_PORT", "5001"))
    debug = os.environ.get("ADMIN_DEBUG") == "1" or os.environ.get("FLASK_DEBUG") == "1"

    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        from waitress import serve

        serve(app, host=host, port=port)
