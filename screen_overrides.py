"""Helpers for resolving per-screen tuning overrides."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

DEFAULT_OVERRIDES_PATH = Path(__file__).with_name("screen_overrides.json")
_ALLOWED_FIELDS = ("font_scale", "image_scale", "device_profile")


@dataclass(frozen=True)
class ResolvedScreenOverride:
    """Effective override values for a screen and display profile."""

    font_scale: Optional[float] = None
    image_scale: Optional[float] = None
    device_profile: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            key: value
            for key, value in {
                "font_scale": self.font_scale,
                "image_scale": self.image_scale,
                "device_profile": self.device_profile,
            }.items()
            if value is not None
        }

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return any(value is not None for value in (self.font_scale, self.image_scale, self.device_profile))


def _empty_block() -> Dict[str, Dict[str, Any]]:
    return {"defaults": {}, "profiles": {}}


def _filter_fields(raw: Mapping[str, Any]) -> Dict[str, Any]:
    filtered: Dict[str, Any] = {}
    for field in _ALLOWED_FIELDS:
        value = raw.get(field)
        if value is not None:
            filtered[field] = value
    return filtered


def load_overrides(path: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Load overrides from *path* and normalise the schema."""

    file_path = Path(path) if path else DEFAULT_OVERRIDES_PATH
    try:
        with file_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}

    screens = payload.get("screens")
    if not isinstance(screens, dict):
        return {}

    result: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for screen_id, raw_entry in screens.items():
        if not isinstance(screen_id, str) or not isinstance(raw_entry, dict):
            continue

        entry = _empty_block()

        raw_defaults = raw_entry.get("defaults")
        if isinstance(raw_defaults, dict):
            entry["defaults"].update(_filter_fields(raw_defaults))

        raw_profiles = raw_entry.get("profiles")
        if isinstance(raw_profiles, dict):
            for profile_name, raw_profile in raw_profiles.items():
                if not isinstance(profile_name, str) or not isinstance(raw_profile, dict):
                    continue
                filtered = _filter_fields(raw_profile)
                if filtered:
                    entry["profiles"][profile_name] = filtered

        legacy_fields = {
            key: value
            for key, value in raw_entry.items()
            if key in _ALLOWED_FIELDS and not isinstance(value, dict)
        }
        if legacy_fields and not entry["defaults"]:
            entry["defaults"].update(legacy_fields)

        if entry["defaults"] or entry["profiles"]:
            result[screen_id] = entry

    return result


def save_overrides(
    overrides: Mapping[str, Mapping[str, Dict[str, Any]]],
    path: Optional[str] = None,
) -> None:
    file_path = Path(path) if path else DEFAULT_OVERRIDES_PATH
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"screens": overrides}
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    tmp_path.replace(file_path)


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return None


def _coerce_resolved(values: Mapping[str, Any]) -> Optional[ResolvedScreenOverride]:
    font_scale = _coerce_float(values.get("font_scale"))
    image_scale = _coerce_float(values.get("image_scale"))
    device_profile = _coerce_str(values.get("device_profile"))
    if font_scale is None and image_scale is None and device_profile is None:
        return None
    return ResolvedScreenOverride(
        font_scale=font_scale,
        image_scale=image_scale,
        device_profile=device_profile,
    )


def resolve_overrides_for_profile(
    display_profile: str,
    *,
    overrides: Optional[Mapping[str, Mapping[str, Dict[str, Any]]]] = None,
) -> Dict[str, ResolvedScreenOverride]:
    """Return overrides for *display_profile*, merging defaults and per-profile entries."""

    source = overrides if overrides is not None else load_overrides()
    resolved: Dict[str, ResolvedScreenOverride] = {}
    for screen_id, entry in source.items():
        defaults = entry.get("defaults") or {}
        profiles = entry.get("profiles") or {}
        profile_values = profiles.get(display_profile, {})
        merged = {**defaults, **profile_values}
        result = _coerce_resolved(merged)
        if result:
            resolved[screen_id] = result
    return resolved


def resolve_override_for_screen(
    screen_id: str,
    display_profile: str,
    *,
    overrides: Optional[Mapping[str, Mapping[str, Dict[str, Any]]]] = None,
) -> Optional[ResolvedScreenOverride]:
    """Resolve the override for ``screen_id`` under ``display_profile``."""

    source = overrides if overrides is not None else load_overrides()
    entry = source.get(screen_id)
    if not entry:
        return None
    defaults = entry.get("defaults") or {}
    profiles = entry.get("profiles") or {}
    profile_values = profiles.get(display_profile, {})
    merged = {**defaults, **profile_values}
    return _coerce_resolved(merged)
