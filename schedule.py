"""Simple frequency-based screen scheduler."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from screens_catalog import SCREEN_IDS
from screens.registry import ScreenDefinition


KNOWN_SCREENS: Set[str] = set(SCREEN_IDS)


@dataclass
class _AlternateSchedule:
    screen_ids: List[str]
    frequency: int
    current_index: int = 0


@dataclass
class _ScheduleEntry:
    screen_id: str
    frequency: int
    cooldown: int = 0
    play_count: int = 0
    alternate: Optional[_AlternateSchedule] = None


class ScreenScheduler:
    """Iterator that yields the next available screen based on frequencies."""

    def __init__(self, entries: Sequence[_ScheduleEntry]):
        self._entries: List[_ScheduleEntry] = list(entries)
        self._cursor: int = 0
        requested: Set[str] = set()
        for entry in self._entries:
            requested.add(entry.screen_id)
            if entry.alternate is not None:
                for screen_id in entry.alternate.screen_ids:
                    requested.add(screen_id)
        self._requested = requested

    @property
    def node_count(self) -> int:
        return len(self._entries)

    @property
    def requested_ids(self) -> Set[str]:
        return set(self._requested)

    def next_available(self, registry: Dict[str, ScreenDefinition]) -> Optional[ScreenDefinition]:
        if not self._entries:
            return None

        for _ in range(len(self._entries)):
            entry = self._entries[self._cursor]
            self._cursor = (self._cursor + 1) % len(self._entries)

            if entry.cooldown > 0:
                entry.cooldown -= 1
                if entry.cooldown > 0:
                    continue

            candidate_id = entry.screen_id
            next_play_count = entry.play_count + 1
            if entry.alternate and entry.alternate.frequency > 0:
                if next_play_count % entry.alternate.frequency == 0:
                    # Get current alternate screen and cycle to next
                    current_screen_id = entry.alternate.screen_ids[entry.alternate.current_index]
                    alt_def = registry.get(current_screen_id)
                    if alt_def and alt_def.available:
                        entry.alternate.current_index = (
                            entry.alternate.current_index + 1
                        ) % len(entry.alternate.screen_ids)
                        entry.play_count = next_play_count
                        # A frequency of ``n`` means the screen should appear once every
                        # ``n`` iterations of the playlist.  The previous implementation
                        # used the raw frequency value as the cooldown which effectively
                        # produced a cycle of ``n + 1`` iterations, making the screens
                        # appear less often than configured (e.g. a frequency of 3 would
                        # yield one appearance every 4 loops).  By resetting the cooldown
                        # to the raw frequency and letting the current iteration proceed
                        # when it hits zero we align the output with the configured
                        # interval while keeping ``0`` as an "always show" value.
                        entry.cooldown = max(entry.frequency, 0)
                        return alt_def
                    if entry.alternate.screen_ids:
                        entry.alternate.current_index = (
                            entry.alternate.current_index + 1
                        ) % len(entry.alternate.screen_ids)

            definition = registry.get(candidate_id)
            if definition and definition.available:
                entry.play_count = next_play_count
                # A frequency of ``n`` means the screen should appear once every
                # ``n`` iterations of the playlist.  The previous implementation
                # used the raw frequency value as the cooldown which effectively
                # produced a cycle of ``n + 1`` iterations, making the screens
                # appear less often than configured (e.g. a frequency of 3 would
                # yield one appearance every 4 loops).  By resetting the cooldown
                # to the raw frequency and letting the current iteration proceed
                # when it hits zero we align the output with the configured
                # interval while keeping ``0`` as an "always show" value.
                entry.cooldown = max(entry.frequency, 0)
                return definition

        return None

    def reset(self) -> None:
        """Reset scheduler state to the initial cursor/cooldown positions."""

        self._cursor = 0
        for entry in self._entries:
            entry.cooldown = 0
            entry.play_count = 0
            if entry.alternate is not None:
                entry.alternate.current_index = 0


def load_schedule_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("Schedule configuration must be a JSON object")
    return data


def build_scheduler(config: Dict[str, Any]) -> ScreenScheduler:
    if not isinstance(config, dict):
        raise ValueError("Schedule configuration must be a JSON object")

    screen_rows = _flatten_config_screens(config)
    if not screen_rows:
        raise ValueError("Configuration must provide a non-empty 'screens' mapping")

    entries: List[_ScheduleEntry] = []
    for screen_id, raw in screen_rows:
        if not isinstance(screen_id, str):
            raise ValueError("Screen identifiers must be strings")
        if screen_id not in KNOWN_SCREENS:
            raise ValueError(f"Unknown screen id '{screen_id}'")
        alternate: Optional[_AlternateSchedule] = None

        if isinstance(raw, dict):
            if "frequency" not in raw:
                raise ValueError(f"Frequency for '{screen_id}' must be provided")
            try:
                frequency = int(raw["frequency"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Frequency for '{screen_id}' must be an integer"
                ) from exc

            alt_spec = raw.get("alt")
            if alt_spec is not None:
                if not isinstance(alt_spec, dict):
                    raise ValueError(
                        f"Alternate configuration for '{screen_id}' must be an object"
                    )
                alt_screen = alt_spec.get("screen")
                alt_frequency = alt_spec.get("frequency")

                # Support both single string and list of strings
                alt_screen_ids: List[str] = []
                if isinstance(alt_screen, str):
                    alt_screen_ids = [alt_screen]
                elif isinstance(alt_screen, list):
                    if not alt_screen:
                        raise ValueError(
                            f"Alternate screen list for '{screen_id}' cannot be empty"
                        )
                    for idx, screen in enumerate(alt_screen):
                        if not isinstance(screen, str):
                            raise ValueError(
                                f"Alternate screen id at index {idx} for '{screen_id}' must be a string"
                            )
                        alt_screen_ids.append(screen)
                else:
                    raise ValueError(
                        f"Alternate screen id for '{screen_id}' must be a string or list of strings"
                    )

                # Validate all screen IDs
                for alt_screen_id in alt_screen_ids:
                    if alt_screen_id not in KNOWN_SCREENS:
                        raise ValueError(
                            f"Unknown alternate screen id '{alt_screen_id}' for '{screen_id}'"
                        )

                try:
                    alt_frequency_int = int(alt_frequency)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Alternate frequency for '{screen_id}' must be an integer"
                    ) from exc
                if alt_frequency_int < 0:
                    raise ValueError(
                        f"Alternate frequency for '{screen_id}' cannot be negative"
                    )
                if alt_frequency_int > 0:
                    alternate = _AlternateSchedule(alt_screen_ids, alt_frequency_int)
        else:
            try:
                frequency = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Frequency for '{screen_id}' must be an integer") from exc

        if frequency < 0:
            raise ValueError(f"Frequency for '{screen_id}' cannot be negative")

        if frequency == 0:
            # A frequency of zero disables the screen.  This allows playlists to
            # keep entries around for future use without removing them from the
            # configuration file while ensuring they never appear in the
            # rotation.
            continue

        entries.append(_ScheduleEntry(screen_id, frequency, alternate=alternate))

    if not entries:
        raise ValueError("Configuration must contain at least one enabled screen")

    return ScreenScheduler(entries)


def _flatten_config_screens(config: Dict[str, Any]) -> List[Tuple[str, Any]]:
    groups = config.get("groups")
    if isinstance(groups, list):
        flattened: List[Tuple[str, Any]] = []
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                raise ValueError(f"Group entry at index {index} must be an object")
            screens = group.get("screens")
            if screens is None:
                continue
            if not isinstance(screens, dict):
                raise ValueError(f"Screens for group at index {index} must be a mapping")
            for screen_id, raw in screens.items():
                flattened.append((screen_id, raw))
        return flattened

    screens = config.get("screens")
    if not isinstance(screens, dict):
        return []
    return list(screens.items())
