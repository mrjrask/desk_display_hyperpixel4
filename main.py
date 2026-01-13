#!/usr/bin/env python3
"""
Main display loop driving the Pimoroni HyperPixel 4.0 Square LCD,
with optional screenshot capture, H.264 MP4 video capture, Wi-Fi triage,
screen-config sequencing, and batch screenshot archiving.

Changes:
- Stop pruning single files; instead, when screenshots/ has >= ARCHIVE_THRESHOLD
  images, archive the whole set into screenshot_archive/<screen>/.
- Avoid creating empty archive folders.
- Guard logo screens when the image file is missing.
- Keep archived screenshots sorted and grouped the same way they are saved
  under screenshots/.
"""
import warnings
from gpiozero.exc import PinFactoryFallback, NativePinFactoryFallback

warnings.filterwarnings("ignore", category=PinFactoryFallback)
warnings.filterwarnings("ignore", category=NativePinFactoryFallback)

import os
import pathlib
import tempfile
import time
import logging
import threading
import datetime
import signal
import shutil
import subprocess
from contextlib import nullcontext
from typing import Callable, Dict, Optional, Set

gc = __import__('gc')


_startup_warnings = []
wifi_utils = None  # type: ignore[assignment]


def _prepare_runtime_dir() -> None:
    """Ensure XDG_RUNTIME_DIR points at a writable directory."""

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir):
        return

    uid_dir = pathlib.Path("/run/user") / str(os.getuid())
    if uid_dir.is_dir():
        os.environ.setdefault("XDG_RUNTIME_DIR", str(uid_dir))
        return

    fallback_dir = pathlib.Path(tempfile.gettempdir()) / f"xdg-runtime-{os.getuid()}"
    try:
        fallback_dir.mkdir(mode=0o700, exist_ok=True)
    except Exception as exc:
        _startup_warnings.append(
            f"Could not create fallback runtime directory '{fallback_dir}': {exc}"
        )
        return

    try:
        fallback_dir.chmod(0o700)
    except Exception:
        pass

    os.environ["XDG_RUNTIME_DIR"] = str(fallback_dir)
    _startup_warnings.append(
        f"XDG_RUNTIME_DIR was unset; using fallback directory '{fallback_dir}'"
    )


# Runtime dependencies are imported lazily to avoid doing heavy work on import.
Image = None
ImageDraw = None
Display = None
ScreenImage = None
animate_fade_in = None
clear_display = None
draw_text_centered = None
clone_font = None
resume_display_updates = None
suspend_display_updates = None
temporary_display_led = None
toggle_brightness = None
data_fetch = None
wifi_utils = None
resolve_storage_paths = None
resolve_config_paths = None
active_config_path = None
draw_date = None
draw_time = None
nixie_frame = None
ScreenContext = None
ScreenDefinition = None
build_screen_registry = None
ScreenScheduler = None
build_scheduler = None
load_schedule_config = None
build_logo_map = None
ResolvedScreenOverride = None
load_screen_overrides = None
resolve_overrides_for_profile = None
required_feeds = None

WIDTH = HEIGHT = SCREEN_DELAY = LOGO_SCREEN_DELAY = SCHEDULE_UPDATE_INTERVAL = None
FONT_DATE_SPORTS = None
ENABLE_SCREENSHOTS = ENABLE_VIDEO = ENABLE_WIFI_MONITOR = VIDEO_FPS = None
CENTRAL_TIME = TRAVEL_ACTIVE_WINDOW = DISPLAY_PROFILE = None

def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.info("🖥️  Starting display service…")

    for _message in _startup_warnings:
        logging.warning(_message)


def _import_runtime_dependencies() -> None:
    global Image, ImageDraw, Display, ScreenImage, animate_fade_in, clear_display
    global draw_text_centered, clone_font, resume_display_updates, suspend_display_updates
    global temporary_display_led, toggle_brightness, data_fetch, wifi_utils
    global resolve_storage_paths, resolve_config_paths, active_config_path
    global draw_date, draw_time
    global nixie_frame, ScreenContext
    global ScreenDefinition, build_screen_registry, ScreenScheduler, build_scheduler
    global load_schedule_config, build_logo_map, ResolvedScreenOverride
    global load_screen_overrides, resolve_overrides_for_profile, required_feeds
    global WIDTH, HEIGHT, SCREEN_DELAY, LOGO_SCREEN_DELAY, SCHEDULE_UPDATE_INTERVAL
    global FONT_DATE_SPORTS, ENABLE_SCREENSHOTS, ENABLE_VIDEO, VIDEO_FPS
    global ENABLE_WIFI_MONITOR, CENTRAL_TIME, TRAVEL_ACTIVE_WINDOW
    global DISPLAY_PROFILE
    global get_travel_active_window, is_travel_screen_active

    from PIL import Image, ImageDraw

    from config import (
        WIDTH,
        HEIGHT,
        SCREEN_DELAY,
        LOGO_SCREEN_DELAY,
        SCHEDULE_UPDATE_INTERVAL,
        FONT_DATE_SPORTS,
        ENABLE_SCREENSHOTS,
        ENABLE_VIDEO,
        VIDEO_FPS,
        ENABLE_WIFI_MONITOR,
        CENTRAL_TIME,
        TRAVEL_ACTIVE_WINDOW,
        DISPLAY_PROFILE,
    )
    from data_feeds import required_feeds
    from utils import (
        Display,
        ScreenImage,
        animate_fade_in,
        clear_display,
        draw_text_centered,
        clone_font,
        resume_display_updates,
        suspend_display_updates,
        temporary_display_led,
        toggle_brightness,
    )
    try:
        import data_fetch
    except ModuleNotFoundError as exc:
        if exc.name == "jwt":
            logging.error(
                "Missing dependency 'PyJWT' (imported as 'jwt'); install with 'pip install \"PyJWT[crypto]\"'."
            )
        raise
    from services import wifi_utils
    from paths import resolve_storage_paths

    from screens.draw_date_time import draw_date, draw_time
    from screens.draw_nixie import nixie_frame
    from screens.draw_travel_time import (
        get_travel_active_window,
        is_travel_screen_active,
    )
    from screens.registry import ScreenContext, ScreenDefinition, build_screen_registry
    from schedule import ScreenScheduler, build_scheduler, load_schedule_config
    from screen_config import active_config_path, resolve_config_paths
    from logos import build_logo_map
    from screen_overrides import (
        ResolvedScreenOverride,
        load_overrides as load_screen_overrides,
        resolve_overrides_for_profile,
    )


# ─── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = ""
CONFIG_LOCAL_PATH = ""
SCREEN_OVERRIDES_PATH = os.path.join(SCRIPT_DIR, "screen_overrides.json")

_storage_paths = None
SCREENSHOT_DIR = ""
CURRENT_SCREENSHOT_DIR = ""
display = None

_initialized = False


# ─── Screenshot archiving (batch) ────────────────────────────────────────────
ARCHIVE_THRESHOLD       = 500  # archive when we reach this many images
SCREENSHOT_ARCHIVE_BASE = ""
ARCHIVE_DEFAULT_FOLDER  = "Screens"
ALLOWED_SCREEN_EXTS     = (".png", ".jpg", ".jpeg")  # images only
_screenshot_file_index: Optional[Set[str]] = None

_screen_config_mtime: Optional[float] = None
screen_scheduler: Optional[ScreenScheduler] = None
_requested_screen_ids: Set[str] = set()
_screen_override_mtime: Optional[float] = None
_resolved_override_cache: Dict[str, ResolvedScreenOverride] = {}

_skip_request_pending = False
_last_screen_id: Optional[str] = None
_SKIP_BUTTON_SCREEN_IDS = {"date", "time"}

_shutdown_event = threading.Event()
_shutdown_complete = threading.Event()
_display_cleared = threading.Event()
_config_server_thread: Optional[threading.Thread] = None


def _initialize_runtime() -> None:
    """Perform runtime-only initialization for the display service."""

    global _storage_paths, SCREENSHOT_DIR, CURRENT_SCREENSHOT_DIR, SCREENSHOT_ARCHIVE_BASE
    global display, LOGOS, _initialized, CONFIG_PATH, CONFIG_LOCAL_PATH

    if _initialized:
        return

    _prepare_runtime_dir()
    _configure_logging()
    _import_runtime_dependencies()

    config_path, config_local_path = resolve_config_paths()
    CONFIG_PATH = str(config_path)
    CONFIG_LOCAL_PATH = str(config_local_path)

    _storage_paths = resolve_storage_paths(logger=logging.getLogger("storage"))
    SCREENSHOT_DIR = str(_storage_paths.screenshot_dir)
    CURRENT_SCREENSHOT_DIR = str(_storage_paths.current_screenshot_dir)
    SCREENSHOT_ARCHIVE_BASE = str(_storage_paths.archive_base)

    display = Display()
    display.hide_mouse_cursor()

    # Ensure the physical panel is cleared immediately so the Raspberry Pi desktop
    # never peeks through while the application performs its initial data fetches.
    clear_display(display)
    if ENABLE_WIFI_MONITOR:
        logging.info("🔌 Starting Wi-Fi monitor…")
        wifi_utils.start_monitor()

    LOGOS = build_logo_map()

    threading.Thread(
        target=_background_refresh,
        daemon=True
    ).start()
    refresh_all()

    _start_config_server()

    _initialized = True

BUTTON_POLL_INTERVAL = 0.1
TOUCHSCREEN_POLL_INTERVAL = 0.25
_BUTTON_NAMES = ("A", "B", "X", "Y")
_BUTTON_STATE = {name: False for name in _BUTTON_NAMES}
_manual_skip_event = threading.Event()
_button_monitor_thread: Optional[threading.Thread] = None
_touch_monitor_thread: Optional[threading.Thread] = None
_touch_device = None


def _load_scheduler_from_config() -> Optional[ScreenScheduler]:
    config_path = str(active_config_path())
    try:
        config_data = load_schedule_config(config_path)
    except Exception as exc:
        logging.warning(f"Could not load schedule configuration: {exc}")
        return None

    try:
        scheduler = build_scheduler(config_data)
    except ValueError as exc:
        logging.error(f"Invalid schedule configuration: {exc}")
        return None

    return scheduler


def _start_config_server() -> None:
    global _config_server_thread

    if _config_server_thread and _config_server_thread.is_alive():
        return

    if os.environ.get("SCREEN_CONFIG_DISABLED") == "1":
        logging.info("🛑 Screen configuration UI disabled via SCREEN_CONFIG_DISABLED.")
        return

    host = os.environ.get("SCREEN_CONFIG_HOST", "0.0.0.0")
    port = int(os.environ.get("SCREEN_CONFIG_PORT", "5001"))

    def _run_server() -> None:
        from admin import app as admin_app
        from waitress import serve

        logging.info("🌐 Screen configuration UI running at http://%s:%s", host, port)
        serve(admin_app, host=host, port=port)

    _config_server_thread = threading.Thread(target=_run_server, daemon=True)
    _config_server_thread.start()


def refresh_schedule_if_needed(force: bool = False) -> None:
    global _screen_config_mtime, screen_scheduler, _requested_screen_ids
    global _last_screen_id, _skip_request_pending

    try:
        mtime = os.path.getmtime(str(active_config_path()))
    except OSError:
        mtime = None

    if not force and mtime == _screen_config_mtime and screen_scheduler is not None:
        return

    scheduler = _load_scheduler_from_config()
    if scheduler is None:
        return

    screen_scheduler = scheduler
    _requested_screen_ids = scheduler.requested_ids
    _screen_config_mtime = mtime
    _last_screen_id = None
    _skip_request_pending = False
    logging.info("🔁 Loaded schedule configuration with %d node(s).", scheduler.node_count)


def _resolved_screen_overrides(force: bool = False) -> Dict[str, ResolvedScreenOverride]:
    global _screen_override_mtime, _resolved_override_cache
    try:
        mtime = os.path.getmtime(SCREEN_OVERRIDES_PATH)
    except OSError:
        mtime = None
    if not force and _screen_override_mtime == mtime:
        return _resolved_override_cache
    overrides = load_screen_overrides(SCREEN_OVERRIDES_PATH)
    _resolved_override_cache = resolve_overrides_for_profile(
        DISPLAY_PROFILE, overrides=overrides
    )
    _screen_override_mtime = mtime
    return _resolved_override_cache

# ─── Display & Wi-Fi monitor ─────────────────────────────────────────────────


def _clear_display_immediately(reason: Optional[str] = None) -> None:
    """Clear the LCD as soon as a shutdown is requested."""

    if display is None:
        return

    already_cleared = _display_cleared.is_set()

    if reason and not already_cleared:
        logging.info("🧹 Clearing display (%s)…", reason)

    try:
        resume_display_updates()
        clear_display(display)
        try:
            display.show()
        except Exception:
            pass
    except Exception:
        pass
    finally:
        _display_cleared.set()
        suspend_display_updates()


def request_shutdown(reason: str) -> None:
    """Signal the main loop to exit and blank the screen immediately."""

    if _shutdown_event.is_set():
        _clear_display_immediately(reason)
        return

    logging.info("✋ Shutdown requested (%s).", reason)
    _shutdown_event.set()
    _clear_display_immediately(reason)


def _restart_desk_display_service() -> None:
    """Restart the desk_display systemd service."""

    request_shutdown("service restart")
    try:
        subprocess.run(
            ["sudo", "systemctl", "restart", "desk_display.service"],
            check=False,
        )
    except Exception as exc:
        logging.error("Failed to restart desk_display.service: %s", exc)


def _check_control_buttons() -> bool:
    """Handle display control buttons.

    Returns True when the caller should skip to the next screen immediately.
    """

    global _skip_request_pending

    if _shutdown_event.is_set():
        return False

    skip_requested = False

    for name in _BUTTON_NAMES:
        try:
            pressed = display.is_button_pressed(name)
        except Exception as exc:
            logging.debug("Button poll failed for %s: %s", name, exc)
            pressed = False

        previously_pressed = _BUTTON_STATE[name]

        if pressed and not previously_pressed:
            if name == "X":
                logging.info("⏭️  X button pressed – skipping to next screen.")
                global _skip_request_pending
                _skip_request_pending = True
                _manual_skip_event.set()
                skip_requested = True
            elif name == "Y":
                logging.info("🔁 Y button pressed – restarting desk_display service…")
                _restart_desk_display_service()
            elif name == "A":
                logging.info("🅰️  A button pressed.")
            elif name == "B":
                logging.info("🅱️  B button pressed.")
        elif not pressed and previously_pressed:
            logging.debug("Button %s released.", name)

        _BUTTON_STATE[name] = pressed

    if skip_requested or _manual_skip_event.is_set():
        return True

    return False


def _wait_with_button_checks(duration: float, on_tick: Optional[Callable[[], None]] = None) -> bool:
    """Sleep for *duration* seconds while checking for control button presses.

    If provided, *on_tick* will be invoked once per poll cycle. Returns True if
    the caller should skip the rest of the current screen.
    """

    if _manual_skip_event.is_set() or _skip_request_pending:
        _manual_skip_event.clear()
        return True

    end = time.monotonic() + duration
    while not _shutdown_event.is_set():
        if _manual_skip_event.is_set() or _skip_request_pending:
            _manual_skip_event.clear()
            return True

        if _check_control_buttons():
            _manual_skip_event.clear()
            return True

        if on_tick:
            try:
                on_tick()
            except Exception as exc:
                logging.debug("Background tick failed: %s", exc)

        remaining = end - time.monotonic()
        if remaining <= 0:
            break

        sleep_for = min(BUTTON_POLL_INTERVAL, remaining)
        if sleep_for > 0:
            if _manual_skip_event.wait(sleep_for):
                _manual_skip_event.clear()
                return True

            if _shutdown_event.is_set():
                return False

    return False


def _monitor_control_buttons() -> None:
    """Background poller to catch brief button presses."""

    logging.debug("Starting control button monitor thread.")

    try:
        while not _shutdown_event.is_set():
            try:
                _check_control_buttons()
            except Exception as exc:
                logging.debug("Button monitor loop failed: %s", exc)

            if _shutdown_event.wait(BUTTON_POLL_INTERVAL):
                break
    finally:
        logging.debug("Control button monitor thread exiting.")


def _find_touchscreen_device():
    """Find the touchscreen input device."""
    try:
        from evdev import InputDevice, ecodes, list_devices
    except ImportError:
        logging.debug("evdev not available; touchscreen support disabled")
        return None

    try:
        for device_path in list_devices():
            try:
                device = InputDevice(device_path)
                # Look for a device that supports absolute positioning (touchscreen)
                caps = device.capabilities()
                if ecodes.EV_ABS in caps and ecodes.EV_KEY in caps:
                    # Check if it has touch capabilities
                    abs_info = caps[ecodes.EV_ABS]
                    has_x = any(code[0] == ecodes.ABS_X or code[0] == ecodes.ABS_MT_POSITION_X for code in abs_info)
                    has_y = any(code[0] == ecodes.ABS_Y or code[0] == ecodes.ABS_MT_POSITION_Y for code in abs_info)
                    if has_x and has_y:
                        logging.info(f"🖱️  Found touchscreen: {device.name} at {device_path}")
                        return device
            except Exception as exc:
                logging.debug(f"Could not check device {device_path}: {exc}")
    except Exception as exc:
        logging.debug(f"Failed to enumerate input devices: {exc}")

    logging.debug("No touchscreen device found")
    return None


def _monitor_touchscreen() -> None:
    """Background monitor for touchscreen taps on the right 1/3 (skip) and bottom-left corner (brightness toggle)."""
    global _touch_device

    try:
        from evdev import InputDevice, ecodes, categorize
    except ImportError:
        logging.debug("evdev not available; touchscreen monitor exiting")
        return
    try:
        from select import select
    except Exception:
        select = None

    _touch_device = _find_touchscreen_device()
    if _touch_device is None:
        logging.debug("Touchscreen monitor exiting (no device found)")
        return

    logging.debug("Starting touchscreen monitor thread.")

    # Get the touchscreen resolution
    try:
        caps = _touch_device.capabilities()
        abs_info = caps.get(ecodes.EV_ABS, [])

        # Find X and Y axis info (try both single-touch and multi-touch)
        x_max = WIDTH
        y_max = HEIGHT
        for code_info in abs_info:
            if code_info[0] in (ecodes.ABS_X, ecodes.ABS_MT_POSITION_X):
                x_max = code_info[1].max
            elif code_info[0] in (ecodes.ABS_Y, ecodes.ABS_MT_POSITION_Y):
                y_max = code_info[1].max

        right_third_threshold = x_max * 2 // 3
        left_third_threshold = x_max // 3
        bottom_third_threshold = y_max * 2 // 3
        min_swipe_distance = x_max // 4
        max_swipe_vertical = y_max // 4
        logging.debug(
            "Touchscreen max: %sx%s, right 1/3: %s, left 1/3: %s, bottom 1/3: %s, swipe min dx: %s, swipe max dy: %s",
            x_max,
            y_max,
            right_third_threshold,
            left_third_threshold,
            bottom_third_threshold,
            min_swipe_distance,
            max_swipe_vertical,
        )
    except Exception as exc:
        logging.warning(f"Could not determine touchscreen resolution: {exc}")
        right_third_threshold = 480  # Default for 720px screen
        left_third_threshold = 240
        bottom_third_threshold = 480
        min_swipe_distance = 180
        max_swipe_vertical = 180

    try:
        last_x = None
        last_y = None
        touch_active = False
        touch_start_x = None
        touch_start_y = None

        def _handle_touch_release() -> None:
            nonlocal last_x, last_y, touch_start_x, touch_start_y, touch_active
            touch_active = False
            swipe_handled = False
            if (
                touch_start_x is not None
                and last_x is not None
                and touch_start_y is not None
                and last_y is not None
            ):
                delta_x = touch_start_x - last_x
                delta_y = abs(touch_start_y - last_y)
                if delta_x >= min_swipe_distance and delta_y <= max_swipe_vertical:
                    logging.info("👈 Swipe right-to-left detected – skipping to next screen.")
                    _manual_skip_event.set()
                    swipe_handled = True
            if not swipe_handled:
                # Check if the touch was in the right 1/3 (skip screen)
                if last_x is not None and last_x >= right_third_threshold:
                    logging.info("👆 Right-side touch detected – skipping to next screen.")
                    _manual_skip_event.set()
                # Check if the touch was in the bottom-left corner (brightness toggle)
                elif last_x is not None and last_y is not None:
                    if last_x <= left_third_threshold and last_y >= bottom_third_threshold:
                        logging.info("💡 Bottom-left corner touch detected – toggling brightness.")
                        toggle_brightness()
            last_x = None
            last_y = None
            touch_start_x = None
            touch_start_y = None

        while not _shutdown_event.is_set():
            try:
                if select is not None:
                    readable, _, _ = select([_touch_device], [], [], TOUCHSCREEN_POLL_INTERVAL)
                    if not readable:
                        continue

                # Set a timeout so we can check shutdown event periodically
                event = _touch_device.read_one()
                if event is None:
                    continue

                # Track touch position
                if event.type == ecodes.EV_ABS:
                    if event.code in (ecodes.ABS_X, ecodes.ABS_MT_POSITION_X):
                        last_x = event.value
                        touch_active = True
                        if touch_start_x is None and touch_active:
                            touch_start_x = last_x
                            touch_start_y = last_y
                    elif event.code in (ecodes.ABS_Y, ecodes.ABS_MT_POSITION_Y):
                        last_y = event.value
                        touch_active = True
                        if touch_start_y is None and touch_active:
                            touch_start_x = last_x
                            touch_start_y = last_y
                    elif event.code in (ecodes.ABS_MT_TRACKING_ID,):
                        # Multi-touch tracking ID -1 means touch released
                        if event.value == -1:
                            if last_x is not None and touch_start_x is None:
                                touch_start_x = last_x
                            if last_y is not None and touch_start_y is None:
                                touch_start_y = last_y
                            _handle_touch_release()
                elif event.type == ecodes.EV_KEY:
                    if event.code == ecodes.BTN_TOUCH:
                        if event.value == 0:  # Touch released
                            _handle_touch_release()
                        elif event.value == 1:  # Touch pressed
                            touch_active = True
                            if touch_start_x is None:
                                touch_start_x = last_x
                                touch_start_y = last_y

            except Exception as exc:
                if _shutdown_event.is_set():
                    break
                logging.debug("Touchscreen monitor loop error: %s", exc)
                time.sleep(TOUCHSCREEN_POLL_INTERVAL)

    except Exception as exc:
        logging.warning("Touchscreen monitor failed: %s", exc)
    finally:
        if _touch_device:
            try:
                _touch_device.close()
            except Exception:
                pass
            _touch_device = None
        logging.debug("Touchscreen monitor thread exiting.")


_button_monitor_thread = threading.Thread(
    target=_monitor_control_buttons,
    name="control-button-monitor",
    daemon=True,
)
_button_monitor_thread.start()

_touch_monitor_thread = threading.Thread(
    target=_monitor_touchscreen,
    name="touchscreen-monitor",
    daemon=True,
)
_touch_monitor_thread.start()


def _next_screen_from_registry(
    registry: Dict[str, ScreenDefinition]
) -> Optional[ScreenDefinition]:
    """Return the next screen, honoring any pending skip requests."""

    global _skip_request_pending

    scheduler = screen_scheduler
    if scheduler is None:
        _skip_request_pending = False
        return None

    entry = scheduler.next_available(registry)
    if entry is None:
        _skip_request_pending = False
        return None

    if not _skip_request_pending:
        return entry

    avoided = set(_SKIP_BUTTON_SCREEN_IDS)
    if _last_screen_id:
        avoided.add(_last_screen_id)

    attempts = scheduler.node_count
    while entry and entry.id in avoided and attempts > 1:
        logging.debug(
            "Manual skip dropping '%s' from queue.",
            entry.id,
        )
        entry = scheduler.next_available(registry)
        attempts -= 1

    if entry and entry.id in avoided:
        logging.debug(
            "Manual skip fallback to '%s' (no alternative available).",
            entry.id,
        )

    _skip_request_pending = False
    return entry


# ─── Screenshot / video outputs ──────────────────────────────────────────────
if ENABLE_SCREENSHOTS:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(CURRENT_SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(SCREENSHOT_ARCHIVE_BASE, exist_ok=True)

video_out = None
if ENABLE_VIDEO:
    import cv2, numpy as np
    FOURCC     = cv2.VideoWriter_fourcc(*"mp4v")
    video_path = os.path.join(SCREENSHOT_DIR, "display_output.mp4")
    logging.info(f"🎥 Starting video capture → {video_path} @ {VIDEO_FPS} FPS using mp4v")
    video_out = cv2.VideoWriter(video_path, FOURCC, VIDEO_FPS, (WIDTH, HEIGHT))
    if not video_out.isOpened():
        logging.error("❌ Cannot open video writer; disabling video output")
        video_out = None

_archive_lock = threading.Lock()


def _release_video_writer() -> None:
    global video_out

    if video_out:
        video_out.release()
        logging.info("🎬 Video finalized cleanly.")
        video_out = None


def _finalize_shutdown() -> None:
    """Run the shutdown cleanup sequence once."""

    if _shutdown_complete.is_set():
        return

    _clear_display_immediately("final cleanup")

    if video_out:
        logging.info("🎬 Finalizing video…")
    _release_video_writer()

    if ENABLE_WIFI_MONITOR and wifi_utils:
        stop_monitor = getattr(wifi_utils, "stop_monitor", None)
        if callable(stop_monitor):
            stop_monitor()

    global _button_monitor_thread, _touch_monitor_thread
    if _button_monitor_thread and _button_monitor_thread.is_alive():
        _button_monitor_thread.join(timeout=1.0)
        _button_monitor_thread = None

    if _touch_monitor_thread and _touch_monitor_thread.is_alive():
        _touch_monitor_thread.join(timeout=1.0)
        _touch_monitor_thread = None

    if display is not None:
        try:
            display.show_mouse_cursor()
        except Exception as exc:
            logging.debug("Failed to show mouse cursor during shutdown: %s", exc)

    _shutdown_complete.set()
    logging.info("👋 Shutdown cleanup finished.")


def _sanitize_directory_name(name: str) -> str:
    """Return a filesystem-friendly directory name while keeping spaces."""

    safe = name.strip().replace("/", "-").replace("\\", "-")
    safe = "".join(ch for ch in safe if ch.isalnum() or ch in (" ", "-", "_"))
    return safe or "Screens"


def _sanitize_filename_prefix(name: str) -> str:
    """Return a filesystem-friendly filename prefix."""

    safe = name.strip().replace("/", "-").replace("\\", "-")
    safe = safe.replace(" ", "_")
    safe = "".join(ch for ch in safe if ch.isalnum() or ch in ("_", "-"))
    return safe or "screen"


def _save_screenshot(sid: str, img: "Image.Image") -> None:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = _sanitize_directory_name(sid)
    prefix = _sanitize_filename_prefix(sid)
    target_dir = os.path.join(SCREENSHOT_DIR, folder)
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, f"{prefix}_{ts}.png")

    try:
        img.save(path)
    except Exception:
        logging.warning(f"⚠️ Screenshot save failed for '{sid}'")
    else:
        _register_screenshot(path)

    current_name = f"{prefix}.png"
    try:
        img.save(os.path.join(CURRENT_SCREENSHOT_DIR, current_name))
    except Exception:
        logging.warning(f"⚠️ Current screenshot save failed for '{sid}'")
    else:
        try:
            for existing in os.listdir(CURRENT_SCREENSHOT_DIR):
                if existing == current_name:
                    continue
                if not existing.startswith(prefix):
                    continue
                to_remove = os.path.join(CURRENT_SCREENSHOT_DIR, existing)
                if os.path.isfile(to_remove) and existing.lower().endswith(ALLOWED_SCREEN_EXTS):
                    os.remove(to_remove)
        except Exception:
            logging.debug("Unable to prune stale current screenshots for '%s'", sid)


def _scan_screenshot_files():
    try:
        results = []
        for root, _dirs, files in os.walk(SCREENSHOT_DIR):
            if os.path.abspath(root) == os.path.abspath(CURRENT_SCREENSHOT_DIR):
                continue
            for fname in files:
                if not fname.lower().endswith(ALLOWED_SCREEN_EXTS):
                    continue
                rel_dir = os.path.relpath(root, SCREENSHOT_DIR)
                rel_path = fname if rel_dir == "." else os.path.join(rel_dir, fname)
                results.append(rel_path)
        return set(results)
    except Exception:
        return set()


def _ensure_screenshot_index() -> Set[str]:
    global _screenshot_file_index
    if _screenshot_file_index is None:
        _screenshot_file_index = _scan_screenshot_files()
    return _screenshot_file_index


def _register_screenshot(path: str) -> None:
    rel_path = os.path.relpath(path, SCREENSHOT_DIR)
    if rel_path and rel_path.lower().endswith(ALLOWED_SCREEN_EXTS):
        _ensure_screenshot_index().add(rel_path)

def maybe_archive_screenshots():
    """
    When screenshots/ reaches ARCHIVE_THRESHOLD images, move the current images
    into screenshot_archive/<screen>/ so the archive mirrors the live
    screenshots/ folder layout. Avoid creating empty archive folders.
    """
    if not ENABLE_SCREENSHOTS:
        return
    index = _ensure_screenshot_index()
    if len(index) < ARCHIVE_THRESHOLD:
        return

    with _archive_lock:
        index = _ensure_screenshot_index()
        if len(index) < ARCHIVE_THRESHOLD:
            return

        moved = 0
        created_dirs = set()
        files = sorted(index)

        for fname in files:
            src = os.path.join(SCREENSHOT_DIR, fname)
            if not os.path.isfile(src):
                index.discard(fname)
                continue
            try:
                parts = fname.split(os.sep)
                if len(parts) > 1:
                    screen_folder, remainder = parts[0], os.path.join(*parts[1:])
                else:
                    screen_folder, remainder = ARCHIVE_DEFAULT_FOLDER, parts[0]

                dest = os.path.join(SCREENSHOT_ARCHIVE_BASE, screen_folder, remainder)
                dest_dir = os.path.dirname(dest)
                if dest_dir and not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                    created_dirs.add(dest_dir)
                shutil.move(src, dest)
                moved += 1
                index.discard(fname)
            except Exception as e:
                logging.warning(f"⚠️  Could not move '{fname}' to archive: {e}")

        if moved == 0:
            for dest_dir in sorted(created_dirs, reverse=True):
                if os.path.isdir(dest_dir) and not os.listdir(dest_dir):
                    try:
                        os.rmdir(dest_dir)
                    except Exception:
                        pass

        if moved:
            logging.info("🗃️  Archived %s screenshot(s) → screenshot_archive/", moved)

# ─── SIGTERM handler ─────────────────────────────────────────────────────────
def _handle_sigterm(signum, frame):
    logging.info("✋ SIGTERM caught—requesting shutdown…")
    request_shutdown("SIGTERM")

signal.signal(signal.SIGTERM, _handle_sigterm)

# ─── Logos ───────────────────────────────────────────────────────────────────
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")

LOGOS: Dict[str, object] = {}

# ─── Data cache & refresh ────────────────────────────────────────────────────
cache = {
    "weather": None,
    "bears":   {"stand": None},
    "hawks":   {"stand": None, "last":None, "live":None, "next":None, "next_home":None},
    "bulls":   {"stand": None, "last":None, "live":None, "next":None, "next_home":None},
    "cubs":    {"stand":None, "last":None, "live":None, "next":None, "next_home":None},
    "sox":     {"stand":None, "last":None, "live":None, "next":None, "next_home":None},
}

_weather_fetched_at: Optional[datetime.datetime] = None
_screen_image_cache: Dict[str, Dict[str, object]] = {}
_last_wifi_state: str = "ok"
_outage_live_games: bool = False

WEATHER_CURRENT_TTL = datetime.timedelta(minutes=20)
WEATHER_HOURLY_TTL = datetime.timedelta(hours=1)

SCOREBOARD_SCREEN_IDS = {
    "NFL Scoreboard",
    "NFL Scoreboard v2",
    "MLB Scoreboard",
    "MLB Scoreboard v2",
    "MLB Scoreboard v3",
    "NBA Scoreboard",
    "NBA Scoreboard v2",
    "NHL Scoreboard",
    "NHL Scoreboard v2",
}

LIVE_SENSITIVE_SCREEN_IDS = {
    *SCOREBOARD_SCREEN_IDS,
    "hawks live",
    "bulls live",
    "cubs live",
    "sox live",
}

def refresh_all():
    global _weather_fetched_at

    if ENABLE_WIFI_MONITOR and wifi_utils:
        wifi_state, _ = wifi_utils.get_wifi_state()
        if wifi_state != "ok":
            logging.info(
                "🔄 Skipping data refresh during Wi-Fi outage (%s).",
                wifi_state,
            )
            return

    feeds = required_feeds(_requested_screen_ids)
    if not feeds:
        logging.info("🔄 Skipping data refresh; no feeds requested.")
        return

    logging.info("🔄 Refreshing data feeds: %s", ", ".join(sorted(feeds)))

    if "weather" in feeds:
        weather = data_fetch.fetch_weather()
        if weather is not None:
            cache["weather"] = weather
            _weather_fetched_at = datetime.datetime.now(CENTRAL_TIME)

    if "bears" in feeds:
        cache["bears"].update({"stand": data_fetch.fetch_bears_standings()})

    if "hawks" in feeds:
        cache["hawks"].update({
            "stand": data_fetch.fetch_blackhawks_standings(),
            "last": data_fetch.fetch_blackhawks_last_game(),
            "live": data_fetch.fetch_blackhawks_live_game(),
            "next": data_fetch.fetch_blackhawks_next_game(),
            "next_home": data_fetch.fetch_blackhawks_next_home_game(),
        })

    if "bulls" in feeds:
        cache["bulls"].update({
            "stand": data_fetch.fetch_bulls_standings(),
            "last": data_fetch.fetch_bulls_last_game(),
            "live": data_fetch.fetch_bulls_live_game(),
            "next": data_fetch.fetch_bulls_next_game(),
            "next_home": data_fetch.fetch_bulls_next_home_game(),
        })

    if "cubs" in feeds:
        cubg = data_fetch.fetch_cubs_games() or {}
        cache["cubs"].update({
            "stand": data_fetch.fetch_cubs_standings(),
            "last": cubg.get("last_game"),
            "live": cubg.get("live_game"),
            "next": cubg.get("next_game"),
            "next_home": cubg.get("next_home_game"),
        })

    if "sox" in feeds:
        soxg = data_fetch.fetch_sox_games() or {}
        cache["sox"].update({
            "stand": data_fetch.fetch_sox_standings(),
            "last": soxg.get("last_game"),
            "live": soxg.get("live_game"),
            "next": soxg.get("next_game"),
            "next_home": soxg.get("next_home_game"),
        })

def _background_refresh() -> None:
    time.sleep(30)
    while not _shutdown_event.is_set():
        refresh_all()
        if _shutdown_event.wait(SCHEDULE_UPDATE_INTERVAL):
            break


def _is_fresh(timestamp: Optional[datetime.datetime], ttl: datetime.timedelta, now: datetime.datetime) -> bool:
    if not timestamp:
        return False
    return now - timestamp <= ttl


def _detect_live_games() -> bool:
    for team in ("hawks", "bulls", "cubs", "sox"):
        if (cache.get(team) or {}).get("live"):
            return True
    return False


def _format_last_connected_time(last_connected: Optional[datetime.datetime]) -> str:
    if not last_connected:
        return "Last connected: unknown"
    stamp = last_connected.strftime("%b %d %I:%M %p")
    stamp = stamp.lstrip("0").replace(" 0", " ")
    return f"Last connected: {stamp}"


def _render_wifi_status_screen(wifi_state: str, wifi_ssid: Optional[str]) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    d = ImageDraw.Draw(img)
    small_font = clone_font(FONT_DATE_SPORTS, 22)
    last_connected = None
    if ENABLE_WIFI_MONITOR and wifi_utils:
        last_connected = wifi_utils.get_last_connected_time()
    last_connected_text = _format_last_connected_time(last_connected)

    if wifi_state == "no_wifi":
        draw_text_centered(d, "No Wi-Fi.", FONT_DATE_SPORTS, y_offset=-12, fill=(255, 0, 0))
        draw_text_centered(d, last_connected_text, small_font, y_offset=22, fill=(255, 255, 0))
    else:
        draw_text_centered(d, "Wi-Fi ok.", FONT_DATE_SPORTS, y_offset=-34, fill=(255, 255, 0))
        draw_text_centered(d, wifi_ssid or "", small_font, y_offset=-8, fill=(255, 255, 0))
        draw_text_centered(d, "No internet.", FONT_DATE_SPORTS, y_offset=16, fill=(255, 0, 0))
        draw_text_centered(d, last_connected_text, small_font, y_offset=44, fill=(255, 255, 0))

    return img


def _apply_outage_rules(
    registry: Dict[str, ScreenDefinition],
    now: datetime.datetime,
    *,
    outage_live_games: bool,
) -> None:
    weather_current_ok = _is_fresh(_weather_fetched_at, WEATHER_CURRENT_TTL, now)
    weather_hourly_ok = _is_fresh(_weather_fetched_at, WEATHER_HOURLY_TTL, now)

    for key in ("weather1", "weather2"):
        if key in registry:
            registry[key].available = registry[key].available and weather_current_ok

    for key in ("weather hourly", "weather radar"):
        if key in registry:
            registry[key].available = registry[key].available and weather_hourly_ok

    if outage_live_games:
        for key in LIVE_SENSITIVE_SCREEN_IDS:
            if key in registry:
                registry[key].available = False

    for key in SCOREBOARD_SCREEN_IDS:
        if key in registry:
            has_cache = bool(_screen_image_cache.get(key, {}).get("image"))
            registry[key].available = registry[key].available and has_cache and not outage_live_games

# ─── Main loop ───────────────────────────────────────────────────────────────
loop_count = 0
_travel_schedule_state: Optional[str] = None

def main_loop():
    global loop_count, _travel_schedule_state, _last_screen_id, _skip_request_pending
    global _last_wifi_state, _outage_live_games

    if not _initialized:
        _initialize_runtime()

    refresh_schedule_if_needed(force=True)

    try:
        while not _shutdown_event.is_set():
            refresh_schedule_if_needed()

            if _manual_skip_event.is_set():
                _manual_skip_event.clear()
                continue

            if _check_control_buttons():
                continue

            # Wi-Fi outage handling
            if ENABLE_WIFI_MONITOR:
                wifi_state, wifi_ssid = wifi_utils.get_wifi_state()
            else:
                wifi_state, wifi_ssid = ("ok", None)

            outage_active = ENABLE_WIFI_MONITOR and wifi_state != "ok"
            if outage_active and _last_wifi_state == "ok":
                _outage_live_games = _detect_live_games()
                logging.info(
                    "📡 Wi-Fi outage detected (%s); live_games=%s",
                    wifi_state,
                    _outage_live_games,
                )
            if not outage_active and _last_wifi_state != "ok":
                _outage_live_games = False
                logging.info("📡 Wi-Fi restored; resuming live data updates.")

            _last_wifi_state = wifi_state

            if outage_active:
                img = _render_wifi_status_screen(wifi_state, wifi_ssid)
                display.image(img)
                display.show()

                if _shutdown_event.is_set():
                    break

                if _wait_with_button_checks(SCREEN_DELAY):
                    gc.collect()
                    continue

            if screen_scheduler is None:
                logging.warning(
                    "No schedule available; sleeping for %s seconds.", SCREEN_DELAY
                )
                if _shutdown_event.is_set():
                    break
                if _wait_with_button_checks(SCREEN_DELAY):
                    continue
                gc.collect()
                continue

            travel_requested = "travel" in _requested_screen_ids
            resolved_overrides = _resolved_screen_overrides()
            now = datetime.datetime.now(CENTRAL_TIME)
            context = ScreenContext(
                display=display,
                cache=cache,
                logos=LOGOS,
                image_dir=IMAGES_DIR,
                images_enabled=True,
                travel_requested=travel_requested,
                travel_active=is_travel_screen_active(),
                travel_window=get_travel_active_window(),
                previous_travel_state=_travel_schedule_state,
                now=now,
                overrides=resolved_overrides,
            )
            registry, metadata = build_screen_registry(context)
            _travel_schedule_state = metadata.get("travel_state", _travel_schedule_state)

            if outage_active:
                _apply_outage_rules(registry, now, outage_live_games=_outage_live_games)

            entry = _next_screen_from_registry(registry)
            if entry is None:
                logging.info(
                    "No eligible screens available; sleeping for %s seconds.",
                    SCREEN_DELAY,
                )
                if _shutdown_event.is_set():
                    break
                if _wait_with_button_checks(SCREEN_DELAY):
                    continue
                gc.collect()
                continue

            sid = entry.id
            loop_count += 1
            logging.info("🎬 Presenting '%s' (iteration %d)", sid, loop_count)

            cached_image = None
            if outage_active and sid in SCOREBOARD_SCREEN_IDS:
                cached_image = _screen_image_cache.get(sid, {}).get("image")

            if isinstance(cached_image, Image.Image):
                result = ScreenImage(image=cached_image.copy(), displayed=False)
            else:
                try:
                    result = entry.render()
                except Exception as exc:
                    logging.error(f"Error in screen '{sid}': {exc}")
                    gc.collect()
                    if _shutdown_event.is_set():
                        break
                    if _wait_with_button_checks(SCREEN_DELAY):
                        continue
                    continue

            if result is None:
                logging.info("Screen '%s' returned no image.", sid)
                gc.collect()
                if _shutdown_event.is_set():
                    break
                if _wait_with_button_checks(SCREEN_DELAY):
                    continue
                continue

            already_displayed = False
            led_override = None
            img = None
            if isinstance(result, ScreenImage):
                img = result.image
                already_displayed = result.displayed
                led_override = result.led_override
            elif isinstance(result, Image.Image):
                img = result

            if isinstance(img, Image.Image) and sid in SCOREBOARD_SCREEN_IDS:
                _screen_image_cache[sid] = {
                    "image": img.copy(),
                    "rendered_at": datetime.datetime.now(CENTRAL_TIME),
                }

            skip_delay = False
            led_context = (
                temporary_display_led(*led_override)
                if led_override is not None
                else nullcontext()
            )
            with led_context:
                if isinstance(img, Image.Image):
                    if "logo" in sid:
                        if ENABLE_SCREENSHOTS:
                            _save_screenshot(sid, img)
                            maybe_archive_screenshots()
                        if ENABLE_VIDEO and video_out:
                            import cv2, numpy as np

                            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                            video_out.write(frame)
                    else:
                        if not already_displayed:
                            animate_fade_in(display, img, steps=15, delay=0.02, easing=True)
                        if ENABLE_SCREENSHOTS:
                            _save_screenshot(sid, img)
                            maybe_archive_screenshots()
                        if ENABLE_VIDEO and video_out:
                            import cv2, numpy as np

                            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                            video_out.write(frame)
                else:
                    logging.info("Screen '%s' produced no drawable image.", sid)

                if _shutdown_event.is_set():
                    break

                _last_screen_id = sid
                delay = LOGO_SCREEN_DELAY if "logo" in sid else SCREEN_DELAY
                nixie_refresh_after = 0.0

                def _refresh_nixie_clock() -> None:
                    nonlocal nixie_refresh_after

                    now_monotonic = time.monotonic()
                    if now_monotonic < nixie_refresh_after:
                        return

                    frame = nixie_frame()
                    try:
                        display.image(frame)
                        if hasattr(display, "show"):
                            display.show()
                    except Exception as exc:
                        logging.debug("Nixie refresh failed: %s", exc)
                    nixie_refresh_after = now_monotonic + 0.5

                on_tick = _refresh_nixie_clock if sid == "nixie" else None
                skip_delay = _wait_with_button_checks(delay, on_tick=on_tick)

            if _shutdown_event.is_set():
                break

            if skip_delay:
                continue
            gc.collect()

    finally:
        _finalize_shutdown()

def main() -> None:
    try:
        main_loop()
    except KeyboardInterrupt:
        logging.info("✋ CTRL-C caught—requesting shutdown…")
        request_shutdown("CTRL-C")
    finally:
        _finalize_shutdown()

    os._exit(0)


if __name__ == '__main__':
    main()
