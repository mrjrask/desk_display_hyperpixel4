#!/usr/bin/env python3
"""Render every available screen to PNG and archive them into a dated ZIP."""
from __future__ import annotations

import argparse
import datetime as _dt
import io
import logging
import os
import sys
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

from PIL import Image

import data_fetch
from config import CENTRAL_TIME, HEIGHT, WIDTH, DISPLAY_PROFILE
from data_feeds import required_feeds
from logos import build_logo_map
from screens.draw_travel_time import get_travel_active_window, is_travel_screen_active
from screens.registry import ScreenContext, ScreenDefinition, build_screen_registry
from screens_catalog import SCREEN_IDS
from schedule import build_scheduler, load_schedule_config
from utils import ScreenImage
from paths import resolve_storage_paths
from screen_overrides import resolve_overrides_for_profile

try:
    import utils
except ImportError:  # pragma: no cover
    utils = None  # type: ignore


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "screens_config.json")
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")

_storage_paths = resolve_storage_paths(logger=logging.getLogger(__name__))
SCREENSHOT_DIR = str(_storage_paths.screenshot_dir)
CURRENT_SCREENSHOT_DIR = str(_storage_paths.current_screenshot_dir)
ARCHIVE_DIR = str(_storage_paths.archive_base)


class HeadlessDisplay:
    """Minimal display stub that captures the latest image frame."""

    def __init__(self, width: int = WIDTH, height: int = HEIGHT):
        self.width = width
        self.height = height
        self._current = Image.new("RGB", (self.width, self.height), "black")

    def clear(self) -> None:
        self._current = Image.new("RGB", (self.width, self.height), "black")

    def image(self, pil_img: Image.Image) -> None:
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        self._current = pil_img.copy()

    def show(self) -> None:  # pragma: no cover - no hardware interaction
        pass

    @property
    def current_image(self) -> Image.Image:
        return self._current


def _sanitize_filename_prefix(name: str) -> str:
    safe = name.strip().replace("/", "-").replace("\\", "-")
    safe = safe.replace(" ", "_")
    safe = "".join(ch for ch in safe if ch.isalnum() or ch in ("_", "-"))
    return safe or "screen"




def build_cache(requested_ids: Optional[Set[str]] = None) -> Dict[str, object]:
    logging.info("Refreshing data feeds…")
    cache: Dict[str, object] = {
        "weather": None,
        "bears": {"stand": None},
        "hawks": {"stand": None, "last": None, "live": None, "next": None, "next_home": None},
        "bulls": {"stand": None, "last": None, "live": None, "next": None, "next_home": None},
        "cubs": {
            "stand": None,
            "last": None,
            "live": None,
            "next": None,
            "next_home": None,
        },
        "sox": {
            "stand": None,
            "last": None,
            "live": None,
            "next": None,
            "next_home": None,
        },
    }

    def _safe_fetch(label: str, func):
        try:
            return func()
        except Exception as exc:
            logging.warning("Data fetch for %s failed: %s", label, exc)
            return None

    feeds = required_feeds(requested_ids or set())
    if not feeds:
        logging.info("No data feeds requested; skipping fetch.")
        return cache

    logging.info("Fetching data feeds: %s", ", ".join(sorted(feeds)))

    if "weather" in feeds:
        cache["weather"] = _safe_fetch("weather", data_fetch.fetch_weather)

    if "bears" in feeds:
        cache["bears"].update({"stand": _safe_fetch("bears standings", data_fetch.fetch_bears_standings)})

    if "hawks" in feeds:
        cache["hawks"].update(
            {
                "stand": _safe_fetch("blackhawks standings", data_fetch.fetch_blackhawks_standings),
                "last": _safe_fetch("blackhawks last game", data_fetch.fetch_blackhawks_last_game),
                "live": _safe_fetch("blackhawks live game", data_fetch.fetch_blackhawks_live_game),
                "next": _safe_fetch("blackhawks next game", data_fetch.fetch_blackhawks_next_game),
                "next_home": _safe_fetch("blackhawks next home game", data_fetch.fetch_blackhawks_next_home_game),
            }
        )

    if "bulls" in feeds:
        cache["bulls"].update(
            {
                "stand": _safe_fetch("bulls standings", data_fetch.fetch_bulls_standings),
                "last": _safe_fetch("bulls last game", data_fetch.fetch_bulls_last_game),
                "live": _safe_fetch("bulls live game", data_fetch.fetch_bulls_live_game),
                "next": _safe_fetch("bulls next game", data_fetch.fetch_bulls_next_game),
                "next_home": _safe_fetch("bulls next home game", data_fetch.fetch_bulls_next_home_game),
            }
        )

    if "cubs" in feeds:
        cubs_games = _safe_fetch("cubs games", data_fetch.fetch_cubs_games) or {}
        cache["cubs"].update(
            {
                "stand": _safe_fetch("cubs standings", data_fetch.fetch_cubs_standings),
                "last": cubs_games.get("last_game"),
                "live": cubs_games.get("live_game"),
                "next": cubs_games.get("next_game"),
                "next_home": cubs_games.get("next_home_game"),
            }
        )

    if "sox" in feeds:
        sox_games = _safe_fetch("sox games", data_fetch.fetch_sox_games) or {}
        cache["sox"].update(
            {
                "stand": _safe_fetch("sox standings", data_fetch.fetch_sox_standings),
                "last": sox_games.get("last_game"),
                "live": sox_games.get("live_game"),
                "next": sox_games.get("next_game"),
                "next_home": sox_games.get("next_home_game"),
            }
        )

    return cache


def load_requested_screen_ids() -> Tuple[set[str], Optional[str]]:
    try:
        config = load_schedule_config(CONFIG_PATH)
        scheduler = build_scheduler(config)
        logging.info("Loaded %d schedule entries", scheduler.node_count)
        return scheduler.requested_ids, None
    except Exception as exc:
        logging.warning("Failed to load schedule configuration: %s", exc)
        return set(), str(exc)


def _extract_image(result: object, display: HeadlessDisplay) -> Optional[Image.Image]:
    if isinstance(result, ScreenImage):
        if result.image is not None:
            return result.image
        if result.displayed:
            return display.current_image.copy()
        return None
    if isinstance(result, Image.Image):
        return result
    return display.current_image.copy()


def _write_zip(assets: Iterable[Tuple[str, Image.Image]], timestamp: _dt.datetime) -> str:
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    zip_name = f"screens_{timestamp.strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = os.path.join(ARCHIVE_DIR, zip_name)

    counts: Dict[str, int] = {}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for screen_id, image in assets:
            prefix = _sanitize_filename_prefix(screen_id)
            counts[prefix] = counts.get(prefix, 0) + 1
            suffix = "" if counts[prefix] == 1 else f"_{counts[prefix] - 1:02d}"
            filename = f"{prefix}{suffix}.png"

            buf = io.BytesIO()
            image.save(buf, format="PNG")
            zf.writestr(filename, buf.getvalue())
    return zip_path


def _write_screenshots(
    assets: Iterable[Tuple[str, Image.Image]], timestamp: _dt.datetime
) -> list[str]:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(CURRENT_SCREENSHOT_DIR, exist_ok=True)
    saved: list[str] = []
    ts_suffix = timestamp.strftime("%Y%m%d_%H%M%S")
    counts: Dict[str, int] = {}
    current_paths: dict[str, str] = {}

    for screen_id, image in assets:
        prefix = _sanitize_filename_prefix(screen_id)
        counts[prefix] = counts.get(prefix, 0) + 1
        suffix = "" if counts[prefix] == 1 else f"_{counts[prefix] - 1:02d}"
        filename = f"{prefix}{suffix}_{ts_suffix}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        image.save(path)
        saved.append(path)

        current_name = f"{prefix}{suffix}.png"
        current_path = os.path.join(CURRENT_SCREENSHOT_DIR, current_name)
        image.save(current_path)
        current_paths[current_name] = current_path

    for existing in os.listdir(CURRENT_SCREENSHOT_DIR):
        existing_path = os.path.join(CURRENT_SCREENSHOT_DIR, existing)
        if existing not in current_paths and os.path.isfile(existing_path):
            try:
                os.remove(existing_path)
            except OSError as exc:
                logging.warning("Failed to remove stale current screenshot '%s': %s", existing_path, exc)

    return saved


def _cleanup_screenshots(saved_paths: Iterable[str]) -> None:
    """Delete screenshot files and prune empty directories."""

    deleted_dirs: set[str] = set()
    for path in saved_paths:
        try:
            os.remove(path)
            deleted_dirs.add(os.path.dirname(path))
        except FileNotFoundError:
            continue
        except OSError as exc:  # pragma: no cover - best-effort cleanup
            logging.warning("Failed to delete screenshot '%s': %s", path, exc)

    for directory in sorted(deleted_dirs, key=len, reverse=True):
        try:
            if os.path.isdir(directory) and not os.listdir(directory):
                os.rmdir(directory)
        except OSError:
            # Directory may not be empty or could have been removed already
            continue


def _suppress_animation_delay():
    if utils is None:
        return lambda: None
    original_sleep = utils.time.sleep

    def restore() -> None:
        utils.time.sleep = original_sleep

    utils.time.sleep = lambda *_args, **_kwargs: None
    return restore


def render_all_screens(
    *,
    sync_screenshots: bool = False,
    create_archive: bool = True,
    ignore_schedule: bool = False,
) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

    restore_sleep = _suppress_animation_delay()
    assets: list[Tuple[str, Image.Image]] = []
    now = _dt.datetime.now(CENTRAL_TIME)
    try:
        display = HeadlessDisplay()
        logos = build_logo_map()
        cache = build_cache(requested_ids)

        schedule_error: Optional[str] = None
        if ignore_schedule:
            logging.info("Ignoring schedule configuration (requested by flag)")
            requested_ids: set[str] = set()
            travel_requested = True
        else:
            requested_ids, schedule_error = load_requested_screen_ids()
            if schedule_error:
                logging.info("Continuing without schedule data (%s)", schedule_error)
            travel_requested = True

        now = _dt.datetime.now(CENTRAL_TIME)
        resolved_overrides = resolve_overrides_for_profile(DISPLAY_PROFILE)
        context = ScreenContext(
            display=display,
            cache=cache,
            logos=logos,
            image_dir=IMAGES_DIR,
            travel_requested=travel_requested,
            travel_active=is_travel_screen_active(),
            travel_window=get_travel_active_window(),
            previous_travel_state=None,
            now=now,
            overrides=resolved_overrides,
        )

        registry, _metadata = build_screen_registry(context)

        ordered_screen_ids: list[str] = []
        missing_screens: list[str] = []

        for screen_id in SCREEN_IDS:
            if screen_id in registry:
                ordered_screen_ids.append(screen_id)
            else:
                missing_screens.append(screen_id)

        if missing_screens:
            logging.warning(
                "Catalog contains %d screen(s) missing from registry: %s",
                len(missing_screens),
                ", ".join(sorted(missing_screens)),
            )

        for screen_id in sorted(registry):
            if screen_id not in ordered_screen_ids:
                ordered_screen_ids.append(screen_id)

        for screen_id in ordered_screen_ids:
            definition: ScreenDefinition = registry[screen_id]
            if definition.available:
                logging.info("Rendering '%s'", screen_id)
            else:
                logging.info("Rendering '%s' (marked unavailable)", screen_id)
            try:
                result = definition.render()
            except Exception as exc:
                logging.error("Failed to render '%s': %s", screen_id, exc)
                continue

            if result is None:
                logging.info("Screen '%s' returned no image.", screen_id)
                continue
            image = _extract_image(result, display)
            if image is None:
                logging.warning("No image returned for '%s'", screen_id)
                continue
            assets.append((screen_id, image))
            display.clear()

    finally:
        restore_sleep()

    if not assets:
        logging.error("No screen images were produced.")
        return 1

    saved: list[str] = []
    if sync_screenshots:
        saved = _write_screenshots(assets, now)
        logging.info(
            "Updated %d screenshot(s) in %s", len(saved), SCREENSHOT_DIR
        )

    if create_archive:
        archive_path = _write_zip(assets, now)
        logging.info("Archived %d screen(s) → %s", len(assets), archive_path)
        print(archive_path)
        if saved:
            _cleanup_screenshots(saved)
            logging.info("Cleaned up %d screenshot file(s) from %s", len(saved), SCREENSHOT_DIR)
    elif not create_archive and not sync_screenshots:
        logging.info("Rendered %d screen(s) (no outputs written)", len(assets))

    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-a",
        "--all",
        dest="ignore_schedule",
        action="store_true",
        help="Ignore screens_config.json and render every available screen.",
    )
    parser.add_argument(
        "--sync-screenshots",
        action="store_true",
        help="Write PNG files for each rendered screen to the screenshots directory.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Skip creating the ZIP archive of rendered screens.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return render_all_screens(
        sync_screenshots=args.sync_screenshots,
        create_archive=not args.no_archive,
        ignore_schedule=args.ignore_schedule,
    )


if __name__ == "__main__":
    sys.exit(main())
