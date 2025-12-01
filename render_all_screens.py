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
from typing import Dict, Iterable, Optional, Tuple

from PIL import Image

import data_fetch
from config import CENTRAL_TIME, HEIGHT, WIDTH, DISPLAY_PROFILE
from screens.draw_travel_time import get_travel_active_window, is_travel_screen_active
from screens.registry import ScreenContext, ScreenDefinition, build_screen_registry
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


def _sanitize_directory_name(name: str) -> str:
    safe = name.strip().replace("/", "-").replace("\\", "-")
    safe = "".join(ch for ch in safe if ch.isalnum() or ch in (" ", "-", "_"))
    return safe or "Screens"


def _sanitize_filename_prefix(name: str) -> str:
    safe = name.strip().replace("/", "-").replace("\\", "-")
    safe = safe.replace(" ", "_")
    safe = "".join(ch for ch in safe if ch.isalnum() or ch in ("_", "-"))
    return safe or "screen"


LOGO_SCREEN_HEIGHT = 370  # 80px base increased by 2.5x for team showcases


def load_logo(
    filename: str,
    height: int = LOGO_SCREEN_HEIGHT,
    width: Optional[int] = None,
) -> Optional[Image.Image]:
    path = os.path.join(IMAGES_DIR, filename)
    try:
        with Image.open(path) as img:
            has_transparency = (
                img.mode in ("RGBA", "LA")
                or (img.mode == "P" and "transparency" in img.info)
            )
            target_mode = "RGBA" if has_transparency else "RGB"
            img = img.convert(target_mode)
            if width is not None and img.width:
                ratio = width / float(img.width)
                target_w = max(1, int(round(img.width * ratio)))
                target_h = max(1, int(round(img.height * ratio)))
            else:
                ratio = height / float(img.height) if img.height else 1
                target_h = max(1, int(round(img.height * ratio))) if img.height else height
                target_w = max(1, int(round(img.width * ratio))) if img.width else max(1, height)
            resized = img.resize((target_w, target_h), Image.ANTIALIAS)
        return resized
    except Exception as exc:
        logging.warning("Logo load failed '%s': %s", filename, exc)
        return None


def build_logo_map() -> Dict[str, Optional[Image.Image]]:
    bears_logo = load_logo("bears.png")
    team_logo_width = bears_logo.width if isinstance(bears_logo, Image.Image) else None

    def _team_logo(path: str) -> Optional[Image.Image]:
        if team_logo_width:
            return load_logo(path, width=team_logo_width)
        return load_logo(path)

    return {
        "weather logo": load_logo("weather.jpg"),
        "verano logo": load_logo("verano.jpg"),
        "bears logo": bears_logo,
        "nfl logo": load_logo("nfl/nfl.png"),
        "hawks logo": _team_logo("hawks.jpg"),
        "nhl logo": load_logo("nhl/nhl.png") or load_logo("nhl/NHL.png"),
        "cubs logo": _team_logo("cubs.jpg"),
        "sox logo": _team_logo("sox.jpg"),
        "mlb logo": load_logo("mlb.jpg"),
        "nba logo": load_logo("nba/NBA.png"),
        "bulls logo": _team_logo("nba/CHI.png"),
    }


def build_cache() -> Dict[str, object]:
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

    cache["weather"] = data_fetch.fetch_weather()
    cache["bears"].update({"stand": data_fetch.fetch_bears_standings()})
    cache["hawks"].update(
        {
            "stand": data_fetch.fetch_blackhawks_standings(),
            "last": data_fetch.fetch_blackhawks_last_game(),
            "live": data_fetch.fetch_blackhawks_live_game(),
            "next": data_fetch.fetch_blackhawks_next_game(),
            "next_home": data_fetch.fetch_blackhawks_next_home_game(),
        }
    )
    cache["bulls"].update(
        {
            "stand": data_fetch.fetch_bulls_standings(),
            "last": data_fetch.fetch_bulls_last_game(),
            "live": data_fetch.fetch_bulls_live_game(),
            "next": data_fetch.fetch_bulls_next_game(),
            "next_home": data_fetch.fetch_bulls_next_home_game(),
        }
    )

    cubs_games = data_fetch.fetch_cubs_games() or {}
    cache["cubs"].update(
        {
            "stand": data_fetch.fetch_cubs_standings(),
            "last": cubs_games.get("last_game"),
            "live": cubs_games.get("live_game"),
            "next": cubs_games.get("next_game"),
            "next_home": cubs_games.get("next_home_game"),
        }
    )

    sox_games = data_fetch.fetch_sox_games() or {}
    cache["sox"].update(
        {
            "stand": data_fetch.fetch_sox_standings(),
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
            folder = _sanitize_directory_name(screen_id)
            prefix = _sanitize_filename_prefix(screen_id)
            counts[prefix] = counts.get(prefix, 0) + 1
            suffix = "" if counts[prefix] == 1 else f"_{counts[prefix] - 1:02d}"
            filename = f"{prefix}{suffix}.png"
            arcname = os.path.join(folder, filename)

            buf = io.BytesIO()
            image.save(buf, format="PNG")
            zf.writestr(arcname, buf.getvalue())
    return zip_path


def _write_screenshots(
    assets: Iterable[Tuple[str, Image.Image]], timestamp: _dt.datetime
) -> list[str]:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    saved: list[str] = []
    ts_suffix = timestamp.strftime("%Y%m%d_%H%M%S")

    for screen_id, image in assets:
        folder = _sanitize_directory_name(screen_id)
        prefix = _sanitize_filename_prefix(screen_id)
        target_dir = os.path.join(SCREENSHOT_DIR, folder)
        os.makedirs(target_dir, exist_ok=True)
        filename = f"{prefix}_{ts_suffix}.png"
        path = os.path.join(target_dir, filename)
        image.save(path)
        saved.append(path)

    return saved


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
        cache = build_cache()

        schedule_error: Optional[str] = None
        if ignore_schedule:
            logging.info("Ignoring schedule configuration (requested by flag)")
            requested_ids: set[str] = set()
            travel_requested = True
        else:
            requested_ids, schedule_error = load_requested_screen_ids()
            if schedule_error:
                logging.info("Continuing without schedule data (%s)", schedule_error)
            travel_requested = "travel" in requested_ids if requested_ids else True

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

        for screen_id in sorted(registry):
            definition: ScreenDefinition = registry[screen_id]
            if not definition.available:
                logging.info("Skipping '%s' (unavailable)", screen_id)
                continue
            logging.info("Rendering '%s'", screen_id)
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

    if sync_screenshots:
        saved = _write_screenshots(assets, now)
        logging.info(
            "Updated %d screenshot(s) in %s", len(saved), SCREENSHOT_DIR
        )

    if create_archive:
        archive_path = _write_zip(assets, now)
        logging.info("Archived %d screen(s) → %s", len(assets), archive_path)
        print(archive_path)
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
