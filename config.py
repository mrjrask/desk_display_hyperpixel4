# config.py

#!/usr/bin/env python3
import datetime
import glob
import json
import logging
import os
import subprocess
from cryptography.hazmat.primitives import serialization
from pathlib import Path
from typing import Optional, Tuple

# ─── Environment helpers ───────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env_file(path: str) -> None:
    """Load simple KEY=VALUE pairs from *path* without overriding existing vars."""

    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return
    except OSError:
        logging.debug("Could not read .env file at %s", path)
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _initialise_env() -> None:
    """Load environment variables from `.env` if present."""

    try:
        from dotenv import load_dotenv  # type: ignore
        from dotenv.main import DotenvParseError  # type: ignore
    except ImportError:
        load_dotenv = None
        DotenvParseError = None

    candidate_paths = []

    project_root = Path(SCRIPT_DIR)
    candidate_paths.append(project_root / ".env")

    cwd_path = Path.cwd() / ".env"
    if cwd_path != candidate_paths[0]:
        candidate_paths.append(cwd_path)

    for path in candidate_paths:
        if not path.is_file():
            continue
        if load_dotenv is not None:
            try:
                load_dotenv(path, override=False)
            except Exception as exc:  # pragma: no cover - defensive against bad env files
                if DotenvParseError is not None and isinstance(exc, DotenvParseError):
                    logging.warning(
                        "Ignoring malformed lines while loading %s: %s; using simple parser instead",
                        path,
                        exc,
                    )
                else:
                    logging.warning(
                        "Failed to load %s with python-dotenv (%s); using simple parser instead",
                        path,
                        exc,
                    )
                _load_env_file(str(path))
        else:
            _load_env_file(str(path))


_ENV_LOADED = False


def _should_load_env() -> bool:
    """Return ``True`` when dotenv files should be loaded."""

    if os.environ.get("DESK_DISPLAY_SKIP_DOTENV"):
        return False

    # Skip filesystem scans when running under pytest to keep test startup fast.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False

    return True


def load_environment() -> None:
    """Load environment variables from `.env` files once, if allowed."""

    global _ENV_LOADED

    if _ENV_LOADED or not _should_load_env():
        return

    _initialise_env()
    _ENV_LOADED = True


load_environment()


def _get_first_env_var(*names: str):
    """Return the first populated environment variable from *names.*"""

    for name in names:
        value = os.environ.get(name)
        if value:
            return value

    return None


def _get_required_env_var(*names: str) -> str:
    value = _get_first_env_var(*names)
    if value:
        return value

    joined = ", ".join(names)
    raise RuntimeError(
        "Missing required environment variable. Set one of: "
        f"{joined}"
    )


def _int_from_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        logging.warning("Invalid %s value %r; using default %d", name, raw_value, default)
        return default
    if value <= 0:
        logging.warning("%s must be greater than zero; using default %d", name, default)
        return default
    return value


def _optional_int_from_env(name: str) -> Optional[int]:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        logging.warning("Invalid %s value %r; ignoring", name, raw_value)
        return None

import pytz
from PIL import Image, ImageDraw, ImageFont

try:
    _RESAMPLE_LANCZOS = Image.Resampling.LANCZOS  # Pillow >= 9.1
except AttributeError:  # pragma: no cover - fallback for older Pillow
    _RESAMPLE_LANCZOS = Image.LANCZOS

# ─── Project paths ────────────────────────────────────────────────────────────
IMAGES_DIR  = os.path.join(SCRIPT_DIR, "images")

# ─── Feature flags ────────────────────────────────────────────────────────────
ENABLE_SCREENSHOTS   = True
ENABLE_VIDEO         = False
VIDEO_FPS            = 30
ENABLE_WIFI_MONITOR  = True

WIFI_RETRY_DURATION  = 180
WIFI_CHECK_INTERVAL  = 60
WIFI_OFF_DURATION    = 180

VRNOF_CACHE_TTL      = 1800

def get_current_ssid():
    try:
        return subprocess.check_output(["iwgetid", "-r"]).decode("utf-8").strip()
    except Exception:
        return None

CURRENT_SSID = get_current_ssid()

# Allow environment variable overrides for latitude/longitude to ensure sync
# across multiple devices (useful when multiple Pis should show same weather)
ENV_LATITUDE  = os.environ.get("LATITUDE")
ENV_LONGITUDE = os.environ.get("LONGITUDE")

if CURRENT_SSID == "Verano":
    ENABLE_WEATHER = True
    LATITUDE       = float(ENV_LATITUDE) if ENV_LATITUDE else 41.9103
    LONGITUDE      = float(ENV_LONGITUDE) if ENV_LONGITUDE else -87.6340
    TRAVEL_MODE    = "to_home"
elif CURRENT_SSID == "wiffy":
    ENABLE_WEATHER = True
    LATITUDE       = float(ENV_LATITUDE) if ENV_LATITUDE else 42.13444
    LONGITUDE      = float(ENV_LONGITUDE) if ENV_LONGITUDE else -87.876389
    TRAVEL_MODE    = "to_work"
else:
    ENABLE_WEATHER = True
    LATITUDE       = float(ENV_LATITUDE) if ENV_LATITUDE else 41.9103
    LONGITUDE      = float(ENV_LONGITUDE) if ENV_LONGITUDE else -87.6340
    TRAVEL_MODE    = "to_home"

WEATHERKIT_TEAM_ID       = os.environ.get("WEATHERKIT_TEAM_ID")
WEATHERKIT_KEY_ID        = os.environ.get("WEATHERKIT_KEY_ID")
WEATHERKIT_SERVICE_ID    = os.environ.get("WEATHERKIT_SERVICE_ID")


def _get_owm_api_key(ssid: Optional[str]) -> Optional[str]:
    if ssid in {"wiffy", "wiffyToo"}:
        return _get_first_env_var("OWM_API_KEY_WIFFY", "OWM_API_KEY")
    if ssid == "Verano":
        return _get_first_env_var("OWM_API_KEY_VERANO", "OWM_API_KEY_DEFAULT")
    return _get_first_env_var("OWM_API_KEY_DEFAULT", "OWM_API_KEY")


OWM_API_KEY = _get_owm_api_key(CURRENT_SSID)


def _normalize_weatherkit_key(key_text: str) -> str:
    stripped = key_text.strip()

    if "\\n" in key_text and "\n" not in key_text:
        logging.warning(
            "WEATHERKIT_PRIVATE_KEY contains literal \\n; converting to newlines"
        )
        key_text = key_text.replace("\\n", "\n")

    if stripped.endswith(".p8") and "BEGIN" not in key_text:
        logging.warning(
            "WEATHERKIT_PRIVATE_KEY looks like a path; set WEATHERKIT_PRIVATE_KEY_PATH instead"
        )

    return key_text


def _validate_weatherkit_private_key(key_text: str, source: str) -> Optional[str]:
    try:
        serialization.load_pem_private_key(
            key_text.encode("utf-8"), password=None
        )
        return key_text
    except Exception as exc:  # pragma: no cover - validation only
        logging.error(
            "WeatherKit private key from %s is not valid PEM; check newline formatting or contents: %s",
            source,
            exc,
        )
        return None


def _load_weatherkit_private_key() -> Optional[str]:
    key_text = os.environ.get("WEATHERKIT_PRIVATE_KEY")
    key_path = os.environ.get("WEATHERKIT_PRIVATE_KEY_PATH")

    if key_path:
        try:
            with open(key_path, "r", encoding="utf-8") as f:
                contents = f.read()
                return _validate_weatherkit_private_key(
                    contents, "WEATHERKIT_PRIVATE_KEY_PATH"
                )
        except Exception as exc:
            logging.error("Failed to read WEATHERKIT_PRIVATE_KEY_PATH: %s", exc)

    if key_text:
        normalized = _normalize_weatherkit_key(key_text)
        return _validate_weatherkit_private_key(
            normalized, "WEATHERKIT_PRIVATE_KEY"
        )
    return None


WEATHERKIT_PRIVATE_KEY = _load_weatherkit_private_key()
WEATHERKIT_API_URL      = os.environ.get(
    "WEATHERKIT_API_URL", "https://weatherkit.apple.com/api/v1/weather"
)
WEATHERKIT_LANGUAGE     = os.environ.get("WEATHERKIT_LANGUAGE", "en")
WEATHER_REFRESH_MINUTES = _int_from_env("WEATHER_REFRESH_MINUTES", 20)
WEATHER_MAX_STALE_MINUTES = _int_from_env("WEATHER_MAX_STALE_MINUTES", 180)

# Log weather location configuration for debugging sync issues
logging.info(
    "Weather location configured: SSID=%s, Lat=%s, Lon=%s %s",
    CURRENT_SSID or "NOT DETECTED",
    LATITUDE,
    LONGITUDE,
    "(from environment)" if ENV_LATITUDE or ENV_LONGITUDE else "(from SSID config)"
)

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

# ─── Display configuration ─────────────────────────────────────────────────────

# Optional override for the bus number used by the inside environmental sensor.
INSIDE_SENSOR_I2C_BUS = _optional_int_from_env("INSIDE_SENSOR_I2C_BUS")


# Supported HyperPixel panels.  The keys roughly match the product names so an
# environment variable such as ``DISPLAY_PROFILE=hyperpixel4`` can be used to
# switch between layouts without having to remember the exact pixel
# dimensions.
_DISPLAY_PROFILES = {
    "hyperpixel4": (800, 480),
    "hyperpixel4_landscape": (800, 480),
    "hyperpixel4_portrait": (480, 800),
    "hyperpixel4_square": (720, 720),
    "hyperpixel4_square_portrait": (720, 720),
}

_DISPLAY_PROFILE_ALIASES = {
    "hp4": "hyperpixel4",
    "hp4_landscape": "hyperpixel4_landscape",
    "hp4_portrait": "hyperpixel4_portrait",
    "hp4_square": "hyperpixel4_square",
    "hp4_square_portrait": "hyperpixel4_square_portrait",
    "landscape": "hyperpixel4_landscape",
    "portrait": "hyperpixel4_portrait",
    "square": "hyperpixel4_square",
    "square_portrait": "hyperpixel4_square_portrait",
    "rect": "hyperpixel4",
    "rectangle": "hyperpixel4",
}


def _normalise_display_profile(name: str) -> str:
    key = name.strip().lower()
    if not key:
        return "hyperpixel4_square"
    canonical = _DISPLAY_PROFILE_ALIASES.get(key, key)
    if canonical not in _DISPLAY_PROFILES:
        logging.warning(
            "Unknown DISPLAY_PROFILE '%s'; defaulting to HyperPixel 4.0 Square (720x720).",
            name,
        )
        return "hyperpixel4_square"
    return canonical


DISPLAY_PROFILE = _normalise_display_profile(
    os.environ.get("DISPLAY_PROFILE", "hyperpixel4_square")
)

DEFAULT_WIDTH, DEFAULT_HEIGHT = _DISPLAY_PROFILES[DISPLAY_PROFILE]

WIDTH = _int_from_env("DISPLAY_WIDTH", DEFAULT_WIDTH)
HEIGHT = _int_from_env("DISPLAY_HEIGHT", DEFAULT_HEIGHT)
IS_SQUARE_DISPLAY = WIDTH == HEIGHT
SCREEN_DELAY = 4
LOGO_SCREEN_DELAY = 1.0
HOURLY_FORECAST_HOURS = _int_from_env("HOURLY_FORECAST_HOURS", 5)
if HOURLY_FORECAST_HOURS < 1:
    HOURLY_FORECAST_HOURS = 1
if HOURLY_FORECAST_HOURS > 12:
    HOURLY_FORECAST_HOURS = 12

BASE_WIDTH = 320
BASE_HEIGHT = 240

SCALE_X = WIDTH / BASE_WIDTH
SCALE_Y = HEIGHT / BASE_HEIGHT
SCALE = min(SCALE_X, SCALE_Y)


_FONT_SCALE_DEFAULT = 1.15
try:
    FONT_SCALE_FACTOR = float(
        os.environ.get("FONT_SCALE_FACTOR", str(_FONT_SCALE_DEFAULT))
    )
    if FONT_SCALE_FACTOR <= 0:
        raise ValueError
except (TypeError, ValueError):
    logging.warning(
        "Invalid FONT_SCALE_FACTOR value; using default %.2f",
        _FONT_SCALE_DEFAULT,
    )
    FONT_SCALE_FACTOR = _FONT_SCALE_DEFAULT


def scale(value: float) -> int:
    return max(1, int(round(value * SCALE)))


def scale_x(value: float) -> int:
    return max(1, int(round(value * SCALE_X)))


def scale_y(value: float) -> int:
    return max(1, int(round(value * SCALE_Y)))


def scale_font(size: float) -> int:
    return max(1, int(round(size * SCALE * FONT_SCALE_FACTOR)))


def get_display_geometry(profile: str) -> Optional[Tuple[int, int]]:
    """Return the (width, height) tuple for ``profile`` if it is known."""

    canonical = _DISPLAY_PROFILE_ALIASES.get(profile, profile)
    return _DISPLAY_PROFILES.get(canonical)


def _load_display_overrides(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("Unable to load display overrides from %s: %s", path, exc)
        return {}

    if isinstance(data, dict):
        return data

    logging.warning("Display overrides in %s must be a JSON object", path)
    return {}


DISPLAY_OVERRIDES_PATH = os.environ.get(
    "DISPLAY_OVERRIDES_PATH", os.path.join(SCRIPT_DIR, "display_overrides.json")
)
DISPLAY_OVERRIDES = _load_display_overrides(DISPLAY_OVERRIDES_PATH)


def _get_font_override(screen_key: str, font_key: str) -> Optional[int]:
    fonts = DISPLAY_OVERRIDES.get("fonts")
    if not isinstance(fonts, dict):
        return None

    screen_fonts = fonts.get(screen_key)
    if not isinstance(screen_fonts, dict):
        return None

    raw_value = screen_fonts.get(font_key)
    if raw_value is None:
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        logging.warning(
            "Invalid font override for %s.%s: %r", screen_key, font_key, raw_value
        )
        return None

    if value <= 0:
        logging.warning(
            "Font override for %s.%s must be greater than zero; ignoring %r",
            screen_key,
            font_key,
            raw_value,
        )
        return None

    return max(1, int(round(value)))


def _font_pixels(screen_key: str, font_key: str, default_size: float) -> int:
    override = _get_font_override(screen_key, font_key)
    if override is not None:
        return override
    return scale_font(default_size)


def _load_screen_font(
    screen_key: str, font_key: str, font_name: str, default_size: float
) -> ImageFont.ImageFont:
    return _load_font(font_name, _font_pixels(screen_key, font_key, default_size))


def _load_emoji_font(size: int) -> ImageFont.ImageFont:
    for noto_path in _iter_font_paths("NotoColorEmoji.ttf"):
        try:
            return ImageFont.truetype(noto_path, size)
        except OSError as exc:
            logging.debug("Unable to load emoji font %s: %s", noto_path, exc)
            for native_size in (109, 128, 160):
                try:
                    return _BitmapEmojiFont(noto_path, native_size, size)
                except OSError as bitmap_exc:
                    logging.debug(
                        "Unable to load bitmap emoji font %s at native size %s: %s",
                        noto_path,
                        native_size,
                        bitmap_exc,
                    )

    symbola_paths = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
    for path in symbola_paths:
        if "symbola" not in path.lower():
            continue
        try:
            return ImageFont.truetype(path, size)
        except OSError as exc:
            logging.debug("Unable to load fallback emoji font %s: %s", path, exc)

    logging.warning("Emoji font not found; falling back to PIL default font")
    return ImageFont.load_default()


def _load_screen_emoji_font(screen_key: str, font_key: str, default_size: float):
    return _load_emoji_font(_font_pixels(screen_key, font_key, default_size))


DISPLAY_BACKEND = os.environ.get("DISPLAY_BACKEND", "auto").strip().lower() or "auto"
DISPLAY_FULLSCREEN = os.environ.get("DISPLAY_FULLSCREEN", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
try:
    TEAM_STANDINGS_DISPLAY_SECONDS = int(
        os.environ.get("TEAM_STANDINGS_DISPLAY_SECONDS", "5")
    )
except (TypeError, ValueError):
    logging.warning(
        "Invalid TEAM_STANDINGS_DISPLAY_SECONDS value; defaulting to 5 seconds."
    )
    TEAM_STANDINGS_DISPLAY_SECONDS = 5
SCHEDULE_UPDATE_INTERVAL = 600

DEFAULT_DISPLAY_ROTATION = 0
try:
    DISPLAY_ROTATION = int(
        os.environ.get("DISPLAY_ROTATION", str(DEFAULT_DISPLAY_ROTATION))
    )
except (TypeError, ValueError):
    logging.warning(
        "Invalid DISPLAY_ROTATION value; defaulting to %d degrees.",
        DEFAULT_DISPLAY_ROTATION,
    )
    DISPLAY_ROTATION = DEFAULT_DISPLAY_ROTATION
if DISPLAY_ROTATION not in {0, 90, 180, 270}:
    logging.warning(
        "Unsupported DISPLAY_ROTATION %d°; defaulting to %d°.",
        DISPLAY_ROTATION,
        DEFAULT_DISPLAY_ROTATION,
    )
    DISPLAY_ROTATION = DEFAULT_DISPLAY_ROTATION

# ─── Font resources ───────────────────────────────────────────────────────────
# Drop your TimesSquare-m105.ttf, DejaVuSans.ttf, and DejaVuSans-Bold.ttf into a
# folder named `fonts` alongside this file. Noto Color Emoji is installed via
# the system package `fonts-noto-color-emoji`.
FONTS_DIR = os.path.join(SCRIPT_DIR, "fonts")


def _iter_font_paths(*names: str):
    seen = set()
    search_roots = [FONTS_DIR, "/usr/share/fonts", "/usr/local/share/fonts"]

    for root in search_roots:
        for name in names:
            direct = os.path.join(root, name)
            if os.path.isfile(direct) and direct not in seen:
                seen.add(direct)
                yield direct

        for name in names:
            for path in glob.glob(os.path.join(root, "**", name), recursive=True):
                if path not in seen and os.path.isfile(path):
                    seen.add(path)
                    yield path


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONTS_DIR, name)
    return ImageFont.truetype(path, size)


def _try_load_font(name: str, size: int):
    path = os.path.join(FONTS_DIR, name)
    if not os.path.isfile(path):
        return None

    try:
        return ImageFont.truetype(path, size)
    except OSError as exc:
        message = str(exc).lower()
        log = logging.debug if "invalid pixel size" in message else logging.warning
        log("Unable to load font %s: %s", path, exc)
        return None


class _BitmapEmojiFont(ImageFont.ImageFont):
    """Scale bitmap-only emoji fonts to an arbitrary size."""

    def __init__(self, path: str, native_size: int, size: int):
        super().__init__()
        self._native_size = native_size
        self.size = size
        self._scale = size / native_size
        self._font = ImageFont.truetype(path, native_size)

    def getbbox(self, text, *args, **kwargs):  # type: ignore[override]
        bbox = self._font.getbbox(text, *args, **kwargs)
        if bbox is None:
            return None
        left, top, right, bottom = bbox
        scale = self._scale
        return (
            int(round(left * scale)),
            int(round(top * scale)),
            int(round(right * scale)),
            int(round(bottom * scale)),
        )

    def getmetrics(self):  # type: ignore[override]
        ascent, descent = self._font.getmetrics()
        scale = self._scale
        return int(round(ascent * scale)), int(round(descent * scale))

    def getsize(self, text, *args, **kwargs):  # type: ignore[override]
        bbox = self.getbbox(text, *args, **kwargs)
        if bbox:
            left, top, right, bottom = bbox
            return right - left, bottom - top
        width, height = self._font.getsize(text, *args, **kwargs)
        scale = self._scale
        return int(round(width * scale)), int(round(height * scale))

    def getlength(self, text, *args, **kwargs):  # type: ignore[override]
        width, _ = self.getsize(text, *args, **kwargs)
        return width

    def _render_native(self, text, *args, **kwargs):
        bbox = self._font.getbbox(text, *args, **kwargs)
        if bbox:
            left, top, right, bottom = bbox
            width = max(1, right - left)
            height = max(1, bottom - top)
        else:
            left = top = 0
            width, height = self._font.getsize(text, *args, **kwargs)

        image = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(image)
        draw.text((-left, -top), text, font=self._font, fill=255)
        return image

    def getmask(self, text, mode="L", *args, **kwargs):  # type: ignore[override]
        base = self._render_native(text, *args, **kwargs)
        scaled = base.resize(
            (
                max(1, int(round(base.width * self._scale))),
                max(1, int(round(base.height * self._scale))),
            ),
            resample=_RESAMPLE_LANCZOS,
        )

        if mode == "1":
            return scaled.convert("1").im
        if mode == "L":
            return scaled.im
        if mode == "RGBA":
            rgba = Image.new("RGBA", scaled.size, (255, 255, 255, 0))
            rgba.putalpha(scaled)
            return rgba.im
        return scaled.im


FONT_DAY_DATE = _load_screen_font("date_time", "day_date", "DejaVuSans-Bold.ttf", 39)
FONT_DATE = _load_screen_font("date_time", "date", "DejaVuSans.ttf", 22)
FONT_TIME = _load_screen_font("date_time", "time", "DejaVuSans-Bold.ttf", 59)
FONT_AM_PM = _load_screen_font("date_time", "am_pm", "DejaVuSans.ttf", 20)

FONT_TEMP = _load_screen_font("weather", "temperature_value", "DejaVuSans-Bold.ttf", 44)
FONT_CONDITION = _load_screen_font("weather", "condition", "DejaVuSans-Bold.ttf", 20)
FONT_WEATHER_DETAILS = _load_screen_font("weather", "details", "DejaVuSans.ttf", 22)
FONT_WEATHER_DETAILS_BOLD = _load_screen_font(
    "weather", "details_bold", "DejaVuSans-Bold.ttf", 18
)
FONT_WEATHER_DETAILS_SMALL = _load_screen_font(
    "weather", "details_small", "DejaVuSans.ttf", 14
)
FONT_WEATHER_DETAILS_SMALL_BOLD = _load_screen_font(
    "weather", "details_small_bold", "DejaVuSans-Bold.ttf", 14
)
FONT_WEATHER_DETAILS_TINY = _load_screen_font(
    "weather", "details_tiny", "DejaVuSans.ttf", 12
)
FONT_WEATHER_DETAILS_MICRO = _load_screen_font(
    "weather", "details_micro", "DejaVuSans.ttf", 11
)
FONT_WEATHER_LABEL = _load_screen_font("weather", "label", "DejaVuSans.ttf", 18)
FONT_EMOJI_SMALL = _load_screen_emoji_font("shared", "emoji_small", 18)

FONT_TITLE_SPORTS = _load_screen_font("sports", "title", "TimesSquare-m105.ttf", 30)
FONT_TEAM_SPORTS = _load_screen_font("sports", "team", "TimesSquare-m105.ttf", 37)
FONT_DATE_SPORTS = _load_screen_font("sports", "date", "TimesSquare-m105.ttf", 30)
FONT_SCORE = _load_screen_font("sports", "score", "TimesSquare-m105.ttf", 41)
FONT_STATUS = _load_screen_font("sports", "status", "TimesSquare-m105.ttf", 30)

# ─── Scoreboard appearance ────────────────────────────────────────────────────

# Scoreboard team name font sizing (used in schedule screens)
SCOREBOARD_NAME_FONT_MIN_SIZE = 36
SCOREBOARD_NAME_FONT_RATIO = 0.45
SCOREBOARD_NAME_FONT_MIN_SIZE_FALLBACK = 20
SCOREBOARD_NAME_FONT_RATIO_FALLBACK = 0.32

# Persistent time display (upper left corner)
PERSISTENT_TIME_ENABLED = True
PERSISTENT_TIME_FONT_SIZE = _font_pixels("shared", "persistent_time", 6)
PERSISTENT_TIME_AMPM_SCALE = 0.6  # AM/PM is 60% of time font size
PERSISTENT_TIME_X = 8
PERSISTENT_TIME_Y = 4
PERSISTENT_TIME_COLOR = (200, 200, 200)


def _coerce_color_component(env_name: str, default: int) -> int:
    """Return a color channel value from 0-255 with logging on invalid input."""

    raw_value = os.environ.get(env_name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        logging.warning(
            "Invalid %s value %r; using default %d", env_name, raw_value, default
        )
        return default

    if not 0 <= value <= 255:
        logging.warning(
            "%s must be between 0 and 255; clamping %d to valid range", env_name, value
        )
        return max(0, min(255, value))

    return value


# Default background color for scoreboards and standings screens. Use an RGB
# tuple so callers can request either RGB or RGBA colors as needed.
SCOREBOARD_BACKGROUND_COLOR = (
    _coerce_color_component("SCOREBOARD_BACKGROUND_R", 0),
    _coerce_color_component("SCOREBOARD_BACKGROUND_G", 0),
    _coerce_color_component("SCOREBOARD_BACKGROUND_B", 0),
)

# Score colors shared across scoreboard implementations.
SCOREBOARD_IN_PROGRESS_SCORE_COLOR = (255, 210, 66)
SCOREBOARD_FINAL_WINNING_SCORE_COLOR = (255, 255, 255)
SCOREBOARD_FINAL_LOSING_SCORE_COLOR = (200, 200, 200)

# ─── Scoreboard scrolling configuration ───────────────────────────────────────
SCOREBOARD_SCROLL_STEP         = 1
SCOREBOARD_SCROLL_DELAY        = 0.02
SCOREBOARD_SCROLL_PAUSE_TOP    = 0.75
SCOREBOARD_SCROLL_PAUSE_BOTTOM = 0.5

# ─── API endpoints ────────────────────────────────────────────────────────────

NHL_API_URL        = "https://api-web.nhle.com/v1/club-schedule-season/CHI/20252026"
MLB_API_URL        = "https://statsapi.mlb.com/api/v1/schedule"
MLB_CUBS_TEAM_ID   = "112"
MLB_SOX_TEAM_ID    = "145"

NBA_TEAM_ID        = "1610612741"
NBA_TEAM_TRICODE   = "CHI"
NBA_IMAGES_DIR     = os.path.join(IMAGES_DIR, "nba")
NBA_FALLBACK_LOGO  = os.path.join(NBA_IMAGES_DIR, "NBA.png")

CENTRAL_TIME = pytz.timezone("America/Chicago")

# Shared sports logo row sizing. This value replaces ad-hoc calculations in the
# team schedule screens so logo heights can be tuned from a single location.
NEXT_GAME_LOGO_FONT_SIZE = scale_y(60)

FONT_INSIDE_LABEL = _load_screen_font("inside", "label", "DejaVuSans-Bold.ttf", 18)
FONT_INSIDE_VALUE = _load_screen_font("inside", "value", "DejaVuSans.ttf", 17)
FONT_TITLE_INSIDE = _load_screen_font("inside", "title", "DejaVuSans-Bold.ttf", 17)
FONT_INSIDE_TEMP = _load_screen_font("inside", "temperature_value", "DejaVuSans-Bold.ttf", 44)

FONT_TRAVEL_TITLE = _load_screen_font("travel", "title", "TimesSquare-m105.ttf", 17)
FONT_TRAVEL_HEADER = _load_screen_font("travel", "header", "TimesSquare-m105.ttf", 17)
FONT_TRAVEL_VALUE = _load_screen_font("travel", "value", "HWYGNRRW.TTF", 26)

FONT_IP_LABEL           = FONT_INSIDE_LABEL
FONT_IP_VALUE           = FONT_INSIDE_VALUE

FONT_STOCK_TITLE = _load_screen_font("vrnof", "title", "DejaVuSans-Bold.ttf", 18)
FONT_STOCK_PRICE = _load_screen_font("vrnof", "price", "DejaVuSans-Bold.ttf", 44)
FONT_STOCK_CHANGE = _load_screen_font("vrnof", "change", "DejaVuSans.ttf", 22)
FONT_STOCK_TEXT = _load_screen_font("vrnof", "text", "DejaVuSans.ttf", 17)

# Standings fonts...
FONT_STAND1_WL = _load_screen_font("mlb_standings", "stand1_wl", "DejaVuSans-Bold.ttf", 34)
FONT_STAND1_RANK = _load_screen_font("mlb_standings", "stand1_rank", "DejaVuSans.ttf", 28)
FONT_STAND1_RANK_COMPACT = _load_screen_font(
    "mlb_standings", "stand1_rank_compact", "DejaVuSans.ttf", 20
)
FONT_STAND1_GB_LABEL = _load_screen_font("mlb_standings", "stand1_gb_label", "DejaVuSans.ttf", 22)
FONT_STAND1_WCGB_LABEL = _load_screen_font(
    "mlb_standings", "stand1_wcgb_label", "DejaVuSans.ttf", 22
)
FONT_STAND1_GB_VALUE = _load_screen_font(
    "mlb_standings", "stand1_gb_value", "DejaVuSans.ttf", 22
)
FONT_STAND1_WCGB_VALUE = _load_screen_font(
    "mlb_standings", "stand1_wcgb_value", "DejaVuSans.ttf", 22
)

FONT_STAND2_RECORD = _load_screen_font(
    "mlb_standings", "stand2_record", "DejaVuSans.ttf", 34
)
FONT_STAND2_LABEL = _load_screen_font("mlb_standings", "stand2_label", "DejaVuSans.ttf", 28)
FONT_STAND2_VALUE = _load_screen_font("mlb_standings", "stand2_value", "DejaVuSans.ttf", 28)

FONT_DIV_HEADER = _load_screen_font("mlb_standings", "div_header", "DejaVuSans-Bold.ttf", 26)
FONT_DIV_RECORD = _load_screen_font("mlb_standings", "div_record", "DejaVuSans.ttf", 28)
FONT_DIV_GB = _load_screen_font("mlb_standings", "div_gb", "DejaVuSans.ttf", 24)
FONT_GB_VALUE = _load_screen_font("mlb_standings", "div_gb_value", "DejaVuSans.ttf", 24)
FONT_GB_LABEL = _load_screen_font("mlb_standings", "div_gb_label", "DejaVuSans.ttf", 20)

FONT_EMOJI = _load_screen_emoji_font("shared", "emoji", 30)

# ─── Screen-specific configuration ─────────────────────────────────────────────

# Weather screen
WEATHER_ICON_SIZE = scale(218)
WEATHER_DESC_GAP  = scale_y(8)

# Date/time screen
DATE_TIME_GH_ICON_INVERT = True
DATE_TIME_GH_ICON_SIZE   = scale(33)
DATE_TIME_GH_ICON_PATHS  = [
    os.path.join(IMAGES_DIR, "gh.png"),
    os.path.join(SCRIPT_DIR, "images", "gh.png"),
]

# Indoor sensor screen colors
INSIDE_COL_BG     = (0, 0, 0)
INSIDE_COL_TITLE  = (240, 240, 240)
INSIDE_CHIP_BLUE  = (34, 124, 236)
INSIDE_CHIP_AMBER = (233, 165, 36)
INSIDE_CHIP_PURPLE = (150, 70, 200)
INSIDE_COL_TEXT   = (255, 255, 255)
INSIDE_COL_STROKE = (230, 230, 230)

# Travel time screen
DEFAULT_WORK_ADDRESS = "224 W Hill St, Chicago, IL"
DEFAULT_HOME_ADDRESS = "3912 Rutgers Ln, Northbrook, IL"

TRAVEL_TO_HOME_ORIGIN = os.environ.get("TRAVEL_TO_HOME_ORIGIN", DEFAULT_WORK_ADDRESS)
TRAVEL_TO_HOME_DESTINATION = os.environ.get(
    "TRAVEL_TO_HOME_DESTINATION", DEFAULT_HOME_ADDRESS
)
TRAVEL_TO_WORK_ORIGIN = os.environ.get(
    "TRAVEL_TO_WORK_ORIGIN", TRAVEL_TO_HOME_DESTINATION
)
TRAVEL_TO_WORK_DESTINATION = os.environ.get(
    "TRAVEL_TO_WORK_DESTINATION", TRAVEL_TO_HOME_ORIGIN
)

TRAVEL_PROFILES = {
    "to_home": {
        "origin": TRAVEL_TO_HOME_ORIGIN,
        "destination": TRAVEL_TO_HOME_DESTINATION,
        "title": "To home:",
        "active_window": (datetime.time(14, 30), datetime.time(19, 0)),
    },
    "to_work": {
        "origin": TRAVEL_TO_WORK_ORIGIN,
        "destination": TRAVEL_TO_WORK_DESTINATION,
        "title": "To work:",
        "active_window": (datetime.time(6, 0), datetime.time(11, 0)),
    },
    "default": {
        "origin": TRAVEL_TO_HOME_ORIGIN,
        "destination": TRAVEL_TO_HOME_DESTINATION,
        "title": "Travel time:",
        "active_window": (datetime.time(6, 0), datetime.time(19, 0)),
    },
}

_travel_profile = TRAVEL_PROFILES.get(TRAVEL_MODE, TRAVEL_PROFILES["default"])
TRAVEL_ORIGIN        = _travel_profile["origin"]
TRAVEL_DESTINATION   = _travel_profile["destination"]
TRAVEL_TITLE         = _travel_profile["title"]
TRAVEL_ACTIVE_WINDOW = _travel_profile["active_window"]
TRAVEL_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"

# Bears schedule screen
# Space between the bottom date label and the display edge on the Bears screen.
# A slightly larger margin keeps the text safely on-screen across devices.
BEARS_BOTTOM_MARGIN = 14
BEARS_SCHEDULE = [
    {"week":"0.1","date":"Sat, Aug 9",  "opponent":"Miami Dolphins",       "home_away":"Home","time":"Noon"},
    {"week":"0.2","date":"Sun, Aug 17", "opponent":"Buffalo Bills",        "home_away":"Home","time":"7PM"},
    {"week":"0.3","date":"Fri, Aug 22", "opponent":"Kansas City Chiefs",   "home_away":"Away","time":"7:20PM"},
    {"week":"Week 1",  "date":"Mon, Sep 8",  "opponent":"Minnesota Vikings",    "home_away":"Home","time":"7:15PM"},
    {"week":"Week 2",  "date":"Sun, Sep 14", "opponent":"Detroit Lions",        "home_away":"Away","time":"Noon"},
    {"week":"Week 3",  "date":"Sun, Sep 21", "opponent":"Dallas Cowboys",       "home_away":"Home","time":"3:25PM"},
    {"week":"Week 4",  "date":"Sun, Sep 28", "opponent":"Las Vegas Raiders",    "home_away":"Away","time":"3:25PM"},
    {"week":"Week 5",  "date":"BYE",         "opponent":"—",                    "home_away":"—",   "time":"—"},
    {"week":"Week 6",  "date":"Mon, Oct 13","opponent":"Washington Commanders", "home_away":"Away","time":"7:15PM"},
    {"week":"Week 7",  "date":"Sun, Oct 19","opponent":"New Orleans Saints",    "home_away":"Home","time":"Noon"},
    {"week":"Week 8",  "date":"Sun, Oct 26","opponent":"Baltimore Ravens",      "home_away":"Away","time":"Noon"},
    {"week":"Week 9",  "date":"Sun, Nov 2", "opponent":"Cincinnati Bengals",    "home_away":"Away","time":"Noon"},
    {"week":"Week 10", "date":"Sun, Nov 9", "opponent":"New York Giants",       "home_away":"Home","time":"Noon"},
    {"week":"Week 11", "date":"Sun, Nov 16","opponent":"Minnesota Vikings",     "home_away":"Away","time":"Noon"},
    {"week":"Week 12", "date":"Sun, Nov 23","opponent":"Pittsburgh Steelers",   "home_away":"Home","time":"Noon"},
    {"week":"Week 13", "date":"Fri, Nov 28","opponent":"Philadelphia Eagles",   "home_away":"Away","time":"2PM"},
    {"week":"Week 14", "date":"Sun, Dec 7", "opponent":"Green Bay Packers",     "home_away":"Away","time":"3:25PM"},
    {"week":"Week 15", "date":"Sun, Dec 14","opponent":"Cleveland Browns",      "home_away":"Home","time":"Noon"},
    {"week":"Week 16", "date":"Sat, Dec 20","opponent":"Green Bay Packers",     "home_away":"Home","time":"7:20PM"},
    {"week":"Week 17", "date":"Sun, Dec 28","opponent":"San Francisco 49ers",   "home_away":"Away","time":"7:20PM"},
    {"week":"Week 18", "date":"TBD",        "opponent":"Detroit Lions",         "home_away":"Home","time":"TBD"},
]

NFL_TEAM_ABBREVIATIONS = {
    "dolphins": "mia",   "bills": "buf",   "chiefs": "kc",
    "vikings": "min",    "lions": "det",   "cowboys": "dal",
    "raiders": "lv",     "commanders": "was","saints": "no",
    "ravens": "bal",     "bengals": "cin",  "giants": "nyg",
    "steelers": "pit",   "eagles": "phi",   "packers": "gb",
    "browns": "cle",     "49ers": "sf",
}

# VRNOF screen
VRNOF_FRESHNESS_LIMIT = 10 * 60
VRNOF_LOTS = [
    {"shares": 125, "cost": 3.39},
    {"shares": 230, "cost": 0.74},
    {"shares": 230, "cost": 1.34},
    {"shares": 555, "cost": 0.75},
    {"shares": 107, "cost": 0.64},
    {"shares": 157, "cost": 0.60},
]

# Hockey assets
NHL_IMAGES_DIR = os.path.join(IMAGES_DIR, "nhl")
TIMES_SQUARE_FONT_PATH = os.path.join(FONTS_DIR, "TimesSquare-m105.ttf")
os.makedirs(NHL_IMAGES_DIR, exist_ok=True)

NHL_API_ENDPOINTS = {
    "team_month_now": "https://api-web.nhle.com/v1/club-schedule/{tric}/month/now",
    "team_season_now": "https://api-web.nhle.com/v1/club-schedule-season/{tric}/now",
    "game_landing": "https://api-web.nhle.com/v1/gamecenter/{gid}/landing",
    "game_boxscore": "https://api-web.nhle.com/v1/gamecenter/{gid}/boxscore",
    "stats_schedule": "https://statsapi.web.nhl.com/api/v1/schedule",
    "stats_feed": "https://statsapi.web.nhl.com/api/v1/game/{gamePk}/feed/live",
}

NHL_TEAM_ID      = 16
NHL_TEAM_TRICODE = "CHI"
NHL_FALLBACK_LOGO = os.path.join(NHL_IMAGES_DIR, "NHL.jpg")
