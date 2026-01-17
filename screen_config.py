"""Helpers for loading and saving screen schedule configuration."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from screens_catalog import SCREEN_IDS


KNOWN_SCREEN_IDS = set(SCREEN_IDS)


def resolve_config_paths() -> tuple[Path, Path]:
    script_dir = Path(__file__).resolve().parent
    default_path = Path(
        os.environ.get("SCREENS_CONFIG_PATH", script_dir / "screens_config.json")
    )
    local_path = Path(
        os.environ.get(
            "SCREENS_CONFIG_LOCAL_PATH",
            default_path.parent / "screens_config.local.json",
        )
    )
    return default_path, local_path


def active_config_path() -> Path:
    default_path, local_path = resolve_config_paths()
    if local_path.exists():
        return local_path
    return default_path


def load_config(path: Path, *, allow_missing: bool = False) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        if allow_missing:
            return {"screens": {}}
        raise

    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object")
    screens = data.get("screens")
    if not isinstance(screens, dict):
        raise ValueError("Configuration must contain a 'screens' mapping")
    return {"screens": screens}


def load_active_config(*, allow_missing: bool = False) -> Dict[str, Any]:
    default_path, local_path = resolve_config_paths()
    if local_path.exists():
        return load_config(local_path, allow_missing=allow_missing)
    return load_config(default_path, allow_missing=allow_missing)


def load_default_config(*, allow_missing: bool = False) -> Dict[str, Any]:
    default_path, _ = resolve_config_paths()
    return load_config(default_path, allow_missing=allow_missing)


def write_config(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    tmp_path.replace(path)


def config_to_ui_list(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    screens = config.get("screens")
    if not isinstance(screens, dict):
        return []

    ui_rows: List[Dict[str, Any]] = []
    for screen_id, raw in screens.items():
        frequency = _coerce_int(raw if not isinstance(raw, dict) else raw.get("frequency"))
        alt_screen = ""
        alt_frequency = ""
        background = ""

        if isinstance(raw, dict):
            alt = raw.get("alt")
            if isinstance(alt, dict):
                alt_screen_value = alt.get("screen")
                if isinstance(alt_screen_value, list):
                    alt_screen = ", ".join(str(item) for item in alt_screen_value)
                elif isinstance(alt_screen_value, str):
                    alt_screen = alt_screen_value
                alt_frequency_value = alt.get("frequency")
                if alt_frequency_value is not None:
                    alt_frequency = str(_coerce_int(alt_frequency_value))
            background_value = raw.get("background")
            if isinstance(background_value, str):
                background = background_value.strip()

        ui_rows.append(
            {
                "id": screen_id,
                "frequency": frequency,
                "alt_screen": alt_screen,
                "alt_frequency": alt_frequency,
                "background": background,
            }
        )
    return ui_rows


def ui_to_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object")

    screens = payload.get("screens")
    if not isinstance(screens, Sequence):
        raise ValueError("Payload must contain a 'screens' list")

    ordered: Dict[str, Any] = {}
    seen = set()

    for index, row in enumerate(screens):
        if not isinstance(row, dict):
            raise ValueError(f"Screen entry at index {index} must be an object")

        screen_id = row.get("id")
        if not isinstance(screen_id, str) or not screen_id.strip():
            raise ValueError("Each screen must include a non-empty id")
        screen_id = screen_id.strip()
        if screen_id not in KNOWN_SCREEN_IDS:
            raise ValueError(f"Unknown screen id '{screen_id}'")
        if screen_id in seen:
            raise ValueError(f"Duplicate screen id '{screen_id}'")
        seen.add(screen_id)

        frequency = _parse_int_field(row.get("frequency"), "Frequency")
        if frequency < 0:
            raise ValueError(f"Frequency for '{screen_id}' cannot be negative")

        alt_screen_raw = row.get("alt_screen", "")
        alt_frequency_raw = row.get("alt_frequency", "")
        background_raw = row.get("background", "")
        background = _parse_text_field(background_raw)

        alt_screen_ids = _parse_alt_screens(alt_screen_raw, screen_id)
        if alt_screen_ids:
            alt_frequency = _parse_int_field(
                alt_frequency_raw,
                "Alternate frequency",
                allow_blank=False,
            )
            if alt_frequency < 0:
                raise ValueError(
                    f"Alternate frequency for '{screen_id}' cannot be negative"
                )
            for alt_id in alt_screen_ids:
                if alt_id not in KNOWN_SCREEN_IDS:
                    raise ValueError(
                        f"Unknown alternate screen id '{alt_id}' for '{screen_id}'"
                    )
            alt_value: Any
            if len(alt_screen_ids) == 1:
                alt_value = alt_screen_ids[0]
            else:
                alt_value = alt_screen_ids
            payload: Dict[str, Any] = {
                "frequency": frequency,
                "alt": {"screen": alt_value, "frequency": alt_frequency},
            }
            if background:
                payload["background"] = background
            ordered[screen_id] = payload
        else:
            if _has_value(alt_frequency_raw):
                raise ValueError(
                    f"Alternate frequency for '{screen_id}' requires alternate screens"
                )
            if background:
                ordered[screen_id] = {"frequency": frequency, "background": background}
            else:
                ordered[screen_id] = frequency

    if not ordered:
        raise ValueError("Configuration must contain at least one screen")

    return {"screens": ordered}


def _parse_alt_screens(raw_value: Any, screen_id: str) -> List[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        parts = [part.strip() for part in raw_value.split(",") if part.strip()]
        return parts
    raise ValueError(
        f"Alternate screens for '{screen_id}' must be a comma-separated string"
    )


def _parse_int_field(value: Any, label: str, *, allow_blank: bool = True) -> int:
    if value is None:
        if allow_blank:
            return 0
        raise ValueError(f"{label} must be provided")
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            if allow_blank:
                return 0
            raise ValueError(f"{label} must be provided")
        value = trimmed
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    return number


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _parse_text_field(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()
