#!/usr/bin/env python3
"""
utils.py

Core utilities for the desk display project:
- Display wrapper
- Drawing helpers
- Animations
- Text wrapping/centering
- Team/MLB helpers
- GitHub update checker
"""
import atexit
import datetime
import html
import os
import random
import subprocess
import threading
import time
import queue
from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import functools
import logging
import math
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

# ─── Pillow compatibility shim ─────────────────────────────────────────────
# Re-add ImageDraw.textsize if missing (Pillow ≥10 compatibility)
import PIL.ImageDraw as _ID
if not hasattr(_ID.ImageDraw, "textsize"):
    def _textsize(self, text, font=None, *args, **kwargs):
        bbox = self.textbbox((0, 0), text, font=font)
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])
    _ID.ImageDraw.textsize = _textsize
# Compatibility for ANTIALIAS (Pillow ≥11)
try:
    Image.ANTIALIAS
except AttributeError:
    Image.ANTIALIAS = Image.Resampling.LANCZOS

try:  # pragma: no cover - optional dependency
    import pygame
except ImportError:  # pragma: no cover - optional dependency
    pygame = None

_ACTIVE_DISPLAY: Optional["Display"] = None
_GITHUB_LED_ANIMATOR: Optional["_GithubLedAnimator"] = None
_GITHUB_LED_STATE: bool = False

_DISPLAY_UPDATE_GATE = threading.Event()
_DISPLAY_UPDATE_GATE.set()
_PYGAME_SHUTDOWN_REGISTERED = False


def _shutdown_pygame() -> None:
    if pygame is None:  # pragma: no cover - optional dependency
        return
    try:  # pragma: no cover - optional dependency cleanup
        pygame.quit()
    except Exception:
        pass


def suspend_display_updates() -> None:
    """Prevent subsequent display updates from reaching the hardware."""

    _DISPLAY_UPDATE_GATE.clear()


def resume_display_updates() -> None:
    """Allow display updates to be pushed to the hardware again."""

    _DISPLAY_UPDATE_GATE.set()


def display_updates_enabled() -> bool:
    """Return True when display updates are currently allowed."""

    return _DISPLAY_UPDATE_GATE.is_set()

LED_INDICATOR_LEVEL = 1 / 255.0

# Project config
from config import (
    WIDTH,
    HEIGHT,
    CENTRAL_TIME,
    DISPLAY_ROTATION,
    DISPLAY_BACKEND,
    DISPLAY_FULLSCREEN,
    DISPLAY_PROFILE,
)
# Color utilities
from screens.color_palettes import random_color
# Colored logging
from colorama import init as colorama_init, Fore, Style
colorama_init(autoreset=True)

# ─── Logging decorator ──────────────────────────────────────────────────────
def log_call(func):
    """
    Decorator that logs entry & exit at DEBUG level only.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logging.debug(f"→ {func.__name__}()")
        result = func(*args, **kwargs)
        logging.debug(f"← {func.__name__}()")
        return result
    return wrapper

# ─── Display wrapper ────────────────────────────────────────────────────────
class Display:
    """Display abstraction supporting kernel-driven and SPI-attached panels."""

    _BUTTON_NAMES = ("A", "B", "X", "Y")

    def __init__(self):
        global _ACTIVE_DISPLAY

        self.width = WIDTH
        self.height = HEIGHT
        self.rotation = DISPLAY_ROTATION % 360
        if self.rotation not in (0, 90, 180, 270):
            logging.warning(
                "Unsupported display rotation %d°; falling back to 0°.",
                self.rotation,
            )
            self.rotation = 0
        self._buffer = Image.new("RGB", (self.width, self.height), "black")
        self._display = None
        self._pygame_surface = None
        self._backend: Optional[str] = None
        self._pygame_recovery_lock = threading.Lock()
        self._pygame_display_lock = threading.RLock()
        self._last_pygame_recovery = 0.0
        self._pygame_present_queue: Optional["queue.Queue[Optional[Image.Image]]"] = None
        self._pygame_present_thread: Optional[threading.Thread] = None
        self._pygame_present_stop = threading.Event()
        self._button_pins: Dict[str, Optional[int]] = {name: None for name in self._BUTTON_NAMES}

        preferred_backend = DISPLAY_BACKEND
        if preferred_backend not in {"auto", "pygame"}:
            logging.warning(
                "Unknown DISPLAY_BACKEND '%s'; falling back to automatic detection.",
                preferred_backend,
            )
            preferred_backend = "auto"

        pygame_error: Optional[str] = None

        if preferred_backend in ("auto", "pygame"):
            success, pygame_error = self._init_pygame_backend()
        else:
            success = False

        if not success:
            reasons = [reason for reason in (pygame_error,) if reason]
            if reasons:
                logging.warning(
                    "Display backend unavailable; running headless (%s).",
                    "; ".join(reasons),
                )
            else:
                logging.warning("Display backend unavailable; running headless.")

        _ACTIVE_DISPLAY = self

    def _hide_mouse_cursor(self) -> None:
        if pygame is None:  # pragma: no cover - optional dependency
            return

        try:
            pygame.mouse.set_visible(False)
        except Exception:  # pragma: no cover - optional dependency
            pass

        # Some platforms only hide the cursor after it has moved. Force a blank
        # cursor surface so it is invisible immediately after startup.
        try:
            transparent = pygame.Surface((1, 1), flags=pygame.SRCALPHA)
            transparent.fill((0, 0, 0, 0))
            invisible_cursor = pygame.cursors.Cursor((0, 0), transparent)
            pygame.mouse.set_cursor(invisible_cursor)
        except Exception:  # pragma: no cover - optional dependency
            pass

        # Some environments require pointer movement before the cursor hides.
        # Nudge the pointer and move it back to encourage the driver to apply
        # the hidden cursor immediately.
        try:
            original_position = pygame.mouse.get_pos()
            pygame.mouse.set_pos((original_position[0] + 1, original_position[1]))
            pygame.mouse.set_pos(original_position)
        except Exception:  # pragma: no cover - optional dependency
            pass

        # SDL 2.30+ (Debian Trixie) can delay applying the hidden cursor until
        # it sees at least one motion event. Inject a no-op motion event so the
        # cursor hides immediately even if the user never touches the mouse.
        try:
            pygame.event.post(
                pygame.event.Event(
                    pygame.MOUSEMOTION,
                    {"pos": pygame.mouse.get_pos(), "rel": (0, 0), "buttons": (0, 0, 0)},
                )
            )
            pygame.event.pump()
        except Exception:  # pragma: no cover - optional dependency
            pass

        # Some KMS/DRM stacks (e.g., HyperPixel 4 on Debian Trixie) keep the
        # hardware cursor visible until relative mouse mode is toggled. Flip it
        # briefly to encourage the cursor plane to disappear, then re-apply the
        # hidden cursor state once more.
        try:
            if hasattr(pygame.mouse, "set_relative"):
                pygame.mouse.set_relative(True)
                pygame.mouse.set_relative(False)
            pygame.mouse.set_visible(False)
        except Exception:  # pragma: no cover - optional dependency
            pass

        try:
            pygame.event.set_grab(True)
        except Exception:  # pragma: no cover - optional dependency
            pass

    def hide_mouse_cursor(self) -> None:
        """Public wrapper to hide the cursor when a mouse is connected."""

        self._hide_mouse_cursor()

    def _init_pygame_backend(self) -> Tuple[bool, Optional[str]]:
        if pygame is None:  # pragma: no cover - optional dependency
            return False, "pygame module not installed"

        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            # Force-disable the hardware cursor when using KMSDRM to ensure it
            # stays hidden on Raspberry Pi/HyperPixel stacks running Trixie.
            os.environ.setdefault("SDL_VIDEO_KMSDRM_DISABLE_CURSOR", "1")

        flags = pygame.FULLSCREEN if DISPLAY_FULLSCREEN else 0
        original_driver = os.environ.get("SDL_VIDEODRIVER")
        driver_candidates: List[Optional[str]] = []
        for candidate in [
            original_driver,
            None,
            "kmsdrm",
            "fbcon",
            "directfb",
            "svgalib",
            "dummy",
        ]:
            if candidate in driver_candidates:
                continue
            driver_candidates.append(candidate)

        attempted_errors: List[str] = []
        surface = None
        try:
            for driver in driver_candidates:
                if driver is None:
                    if original_driver is None:
                        os.environ.pop("SDL_VIDEODRIVER", None)
                    else:
                        os.environ["SDL_VIDEODRIVER"] = original_driver
                else:
                    os.environ["SDL_VIDEODRIVER"] = driver

                try:
                    pygame.display.quit()
                except Exception:  # pragma: no cover - optional dependency cleanup
                    pass

                try:
                    pygame.display.init()
                    surface = pygame.display.set_mode((self.width, self.height), flags)
                except Exception as exc:
                    attempted_errors.append(f"{driver or 'default'}: {exc}")
                    try:
                        pygame.display.quit()
                    except Exception:  # pragma: no cover - optional dependency cleanup
                        pass
                    surface = None
                    continue

                if surface:
                    break

            if surface is None:
                if attempted_errors:
                    return False, ", ".join(attempted_errors)
                return False, "pygame display initialisation failed"

            try:
                pygame.display.set_caption("Desk Display")
            except Exception:  # pragma: no cover - optional dependency
                pass
            self._hide_mouse_cursor()
            try:
                surface.fill((0, 0, 0))
                pygame.display.flip()
            except Exception:  # pragma: no cover - optional dependency
                pass

            global _PYGAME_SHUTDOWN_REGISTERED
            if not _PYGAME_SHUTDOWN_REGISTERED:
                _PYGAME_SHUTDOWN_REGISTERED = True
                atexit.register(_shutdown_pygame)

            with self._pygame_display_lock:
                self._pygame_surface = surface
                self._backend = "pygame"
            self._start_pygame_presenter()
            logging.info(
                "🖼️  Pygame display initialized for %s (%dx%d, rotation %d°).",
                DISPLAY_PROFILE,
                self.width,
                self.height,
                self.rotation,
            )
            return True, None
        finally:
            if original_driver is None:
                os.environ.pop("SDL_VIDEODRIVER", None)
            else:
                os.environ["SDL_VIDEODRIVER"] = original_driver

    def _pygame_present_loop(self) -> None:
        if pygame is None:
            return
        queue_obj = self._pygame_present_queue
        if queue_obj is None:
            return
        while not self._pygame_present_stop.is_set():
            try:
                frame = queue_obj.get(timeout=0.5)
            except queue.Empty:
                continue
            if frame is None:
                break
            try:
                self._present_pygame_frame(frame)
            except Exception as exc:
                logging.warning("Pygame presenter loop failed: %s", exc)

    def _present_pygame_frame(self, frame: Image.Image) -> None:
        if pygame is None:
            return
        with self._pygame_display_lock:
            if self._pygame_surface is None:
                return
            try:
                frame_bytes = frame.tobytes()
                frame_surface = pygame.image.frombuffer(
                    frame_bytes,
                    frame.size,
                    frame.mode,
                )
                if self.rotation:
                    frame_surface = pygame.transform.rotate(frame_surface, self.rotation)
                frame_surface = frame_surface.convert()
                target_size = self._pygame_surface.get_size()
                if frame_surface.get_size() != target_size:
                    frame_surface = pygame.transform.smoothscale(frame_surface, target_size)
                self._pygame_surface.blit(frame_surface, (0, 0))
                pygame.display.flip()
                try:
                    pygame.event.pump()
                except Exception:  # pragma: no cover - optional dependency
                    pass
            except Exception as exc:
                logging.warning("Pygame display refresh failed: %s", exc)
                self._attempt_pygame_recovery(str(exc))

    def _start_pygame_presenter(self) -> None:
        if pygame is None:
            return
        if self._backend != "pygame":
            return

        # Reinforce cursor hiding whenever the presenter starts or restarts.
        self._hide_mouse_cursor()
        if self._pygame_present_queue is None:
            self._pygame_present_queue = queue.Queue(maxsize=1)
        if self._pygame_present_thread and self._pygame_present_thread.is_alive():
            return
        self._pygame_present_stop.clear()
        thread = threading.Thread(
            target=self._pygame_present_loop,
            name="pygame-presenter",
            daemon=True,
        )
        self._pygame_present_thread = thread
        try:
            thread.start()
        except Exception as exc:
            logging.debug("Failed to start pygame presenter thread: %s", exc)
            self._pygame_present_thread = None

    def _stop_pygame_presenter(self) -> None:
        queue_obj = self._pygame_present_queue
        thread = self._pygame_present_thread
        self._pygame_present_stop.set()
        if queue_obj is not None:
            try:
                queue_obj.put_nowait(None)
            except queue.Full:
                pass
            except Exception:
                pass
        if thread and thread.is_alive():
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass
        self._pygame_present_thread = None
        self._pygame_present_queue = None

    def _update_display(self):
        if not display_updates_enabled():
            return
        if self._backend == "pygame" and pygame is not None:
            if self._pygame_present_queue is None:
                self._start_pygame_presenter()
            queue_obj = self._pygame_present_queue
            if queue_obj is None:
                return
            frame = self._buffer.copy()
            if frame.mode != "RGB":
                frame = frame.convert("RGB")
            try:
                while True:
                    queue_obj.get_nowait()
            except queue.Empty:
                pass
            try:
                queue_obj.put_nowait(frame)
            except queue.Full:
                pass
            return

        if self._display is None:  # pragma: no cover - hardware import
            return
        try:
            buffer_to_display = self._buffer
            if self.rotation:
                buffer_to_display = self._buffer.rotate(self.rotation, expand=False)
            self._display.buffer = buffer_to_display
            self._display.display()
        except Exception as exc:  # pragma: no cover - hardware import
            logging.warning("Display refresh failed: %s", exc)

    def _attempt_pygame_recovery(self, error_message: str) -> None:
        """Try to recover the pygame display after driver-level failures."""

        if pygame is None or self._backend != "pygame":
            return

        lower_msg = error_message.lower()
        if "egl" not in lower_msg and "context" not in lower_msg:
            return

        now = time.monotonic()
        if now - self._last_pygame_recovery < 5:
            return

        with self._pygame_recovery_lock:
            if now - self._last_pygame_recovery < 5:
                return

            self._last_pygame_recovery = now
            logging.info("🔄 Attempting to reset pygame display after EGL failure…")
            with self._pygame_display_lock:
                self._pygame_surface = None
                try:
                    pygame.display.quit()
                except Exception:
                    pass

                success, reason = self._init_pygame_backend()
            if success:
                self._hide_mouse_cursor()
                logging.info("✅ Pygame display reset succeeded.")
                self._start_pygame_presenter()
                return

            if reason:
                logging.error("Pygame display reset failed: %s", reason)
            else:
                logging.error("Pygame display reset failed for an unknown reason.")

    def clear(self):
        self._buffer = Image.new("RGB", (self.width, self.height), "black")
        self._update_display()

    def image(self, pil_img: Image.Image):
        if pil_img.size != (self.width, self.height):
            pil_img = pil_img.resize((self.width, self.height), Image.ANTIALIAS)
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        self._buffer = pil_img.copy()
        self._update_display()

    def show(self):
        # No additional action required; display() is triggered during image()
        self._update_display()

    def capture(self) -> Image.Image:
        """Return a copy of the currently buffered frame."""

        return self._buffer.copy()

    # ----- Hardware helpers -------------------------------------------------
    def set_led(self, r: float = 0.0, g: float = 0.0, b: float = 0.0) -> None:
        """Set the onboard RGB LED, if hardware is available."""

        if self._display is None:  # pragma: no cover - hardware import
            return
        try:  # pragma: no cover - hardware import
            self._display.set_led(r=r, g=g, b=b)
        except Exception as exc:  # pragma: no cover - hardware import
            logging.debug("Display LED update failed: %s", exc)

    def is_button_pressed(self, name: str) -> bool:
        """Return True if the named button is currently pressed."""

        if self._display is None:  # pragma: no cover - hardware import
            return False

        pin = self._button_pins.get(name.upper())
        if pin is None:  # pragma: no cover - hardware import
            return False

        try:  # pragma: no cover - hardware import
            raw_state = self._display.read_button(pin)
        except Exception as exc:  # pragma: no cover - hardware import
            logging.debug("Display button read failed (%s): %s", name, exc)
            return False

        if isinstance(raw_state, bool):  # pragma: no cover - hardware import
            return raw_state

        if isinstance(raw_state, (int, float)):  # pragma: no cover - hardware import
            # Buttons are wired active-low; a ``0`` reading means the button is
            # being held down.  ``read_button`` previously returned ``True``
            # when pressed but newer firmware returns the raw ``0/1`` GPIO
            # value.  Treat both styles uniformly so the skip button works
            # regardless of driver version.
            return raw_state == 0

        return bool(raw_state)


def get_active_display() -> Optional["Display"]:
    """Return the most recently constructed :class:`Display` instance, if any."""

    return _ACTIVE_DISPLAY


@dataclass
class ScreenImage:
    """Container for a rendered screen image.

    Attributes
    ----------
    image:
        The full PIL image representing the screen.
    displayed:
        Whether the image has already been pushed to the display by the
        originating function. This allows callers to skip redundant redraws
        while still accessing the image data (e.g., for screenshots).
    led_override:
        Optional RGB tuple describing an LED color override that should remain
        active while the image is shown.
    """

    image: Image.Image
    displayed: bool = False
    led_override: Optional[Tuple[float, float, float]] = None

# ─── Basic utilities ────────────────────────────────────────────────────────
@log_call
def clear_display(display):
    """
    Clear the connected display, falling back to a blank frame.
    """
    try:
        display.clear()
    except Exception:
        try:
            blank = Image.new("RGB", (getattr(display, "width", WIDTH), getattr(display, "height", HEIGHT)), "black")
            display.image(blank)
            display.show()
        except Exception:
            pass

@log_call
def draw_text_centered(
    draw: ImageDraw.Draw,
    text: str,
    font: ImageFont.FreeTypeFont,
    y_offset: int = 0,
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    fill=(255,255,255)
):
    """
    Draw `text` centered horizontally at vertical center + y_offset.
    """
    w, h = draw.textsize(text, font=font)
    x = (width - w) // 2
    y = (height - h) // 2 + y_offset
    draw.text((x, y), text, font=font, fill=fill)

@log_call
def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int):
    """
    Break `text` into lines so each line fits within max_width.
    """
    words = text.split()
    if not words:
        return []
    dummy = Image.new("RGB", (max_width, 1))
    draw = ImageDraw.Draw(dummy)
    lines = [words[0]]
    for w in words[1:]:
        test = f"{lines[-1]} {w}"
        if draw.textsize(test, font=font)[0] <= max_width:
            lines[-1] = test
        else:
            lines.append(w)
    return lines


def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    try:
        return draw.textsize(text, font=font)
    except Exception:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return right - left, bottom - top


def clone_font(font: ImageFont.FreeTypeFont, size: int) -> ImageFont.FreeTypeFont:
    path = getattr(font, "path", None)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return font


def fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    base_font: ImageFont.FreeTypeFont,
    max_width: int,
    max_height: int,
    *,
    min_pt: int = 8,
    max_pt: int | None = None,
) -> ImageFont.FreeTypeFont:
    base_size = getattr(base_font, "size", 16)
    hi = max_pt if max_pt else base_size
    lo = min_pt
    best = clone_font(base_font, lo)
    while lo <= hi:
        mid = (lo + hi) // 2
        test_font = clone_font(base_font, mid)
        width, height = measure_text(draw, text, test_font)
        if width <= max_width and height <= max_height:
            best = test_font
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def format_voc_ohms(value) -> str:
    if value is None:
        return "N/A"
    try:
        val = float(value)
    except Exception:
        return "N/A"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f} MΩ"
    if val >= 1_000:
        return f"{val / 1_000:.1f} kΩ"
    return f"{val:.0f} Ω"


def temperature_color(temp_f: float, lo: float = 50.0, hi: float = 80.0) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, (temp_f - lo) / (hi - lo + 1e-6)))
    if t < 0.5:
        alpha = t / 0.5
        r = int(0 + (80 - 0) * alpha)
        g = int(150 + (220 - 150) * alpha)
        b = int(255 + (180 - 255) * alpha)
    else:
        alpha = (t - 0.5) / 0.5
        r = int(80 + (255 - 80) * alpha)
        g = int(220 + (120 - 220) * alpha)
        b = int(180 + (0 - 180) * alpha)
    return (r, g, b)


def draw_persistent_time(img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """
    Draw the current time in the upper left corner of the screen.
    Time format: "3:23 PM" or "12:45 AM"
    AM/PM font size is 60% of the time font size.
    """
    from config import (
        PERSISTENT_TIME_ENABLED,
        PERSISTENT_TIME_FONT_SIZE,
        PERSISTENT_TIME_AMPM_SCALE,
        PERSISTENT_TIME_X,
        PERSISTENT_TIME_Y,
        PERSISTENT_TIME_COLOR,
        CENTRAL_TIME,
    )

    if not PERSISTENT_TIME_ENABLED:
        return

    try:
        now = datetime.datetime.now(CENTRAL_TIME)
        # Format time
        hour = now.hour
        minute = now.minute
        am_pm = "AM" if hour < 12 else "PM"

        # Convert to 12-hour format
        if hour == 0:
            hour = 12
        elif hour > 12:
            hour = hour - 12

        time_str = f"{hour}:{minute:02d}"

        # Load fonts
        from config import FONTS_DIR
        time_font_size = PERSISTENT_TIME_FONT_SIZE
        ampm_font_size = max(1, int(round(time_font_size * PERSISTENT_TIME_AMPM_SCALE)))

        time_font = ImageFont.truetype(os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf"), time_font_size)
        ampm_font = ImageFont.truetype(os.path.join(FONTS_DIR, "DejaVuSans.ttf"), ampm_font_size)

        # Get text sizes
        try:
            time_bbox = draw.textbbox((0, 0), time_str, font=time_font)
            time_width = time_bbox[2] - time_bbox[0]
            time_height = time_bbox[3] - time_bbox[1]
            ampm_bbox = draw.textbbox((0, 0), am_pm, font=ampm_font)
            ampm_width = ampm_bbox[2] - ampm_bbox[0]
            ampm_height = ampm_bbox[3] - ampm_bbox[1]
        except Exception:
            time_width, time_height = draw.textsize(time_str, font=time_font)
            ampm_width, ampm_height = draw.textsize(am_pm, font=ampm_font)

        # Draw time
        x = PERSISTENT_TIME_X
        y = PERSISTENT_TIME_Y
        draw.text((x, y), time_str, font=time_font, fill=PERSISTENT_TIME_COLOR)

        # Draw AM/PM to the right of time
        spacing = 4
        ampm_x = x + time_width + spacing
        ampm_y = y + (time_height - ampm_height) // 2  # Center vertically with time
        draw.text((ampm_x, ampm_y), am_pm, font=ampm_font, fill=PERSISTENT_TIME_COLOR)

    except Exception as exc:
        # Silently fail if there's any issue drawing the time
        logging.debug("Failed to draw persistent time: %s", exc)


@log_call
def _ease_in_out_cubic(t: float) -> float:
    """
    Cubic easing function for smooth transitions.
    Starts slow, speeds up in middle, slows down at end.
    """
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2


def animate_fade_in(
    display: Display,
    new_image: Image.Image,
    steps: int = 10,
    delay: float = 0.02,
    *,
    from_image: Image.Image | None = None,
    easing: bool = True,
    fade_through_black: bool = False,
):
    """
    Fade from the current display buffer (or ``from_image``) into ``new_image``.

    Args:
        display: The display device
        new_image: The target image to fade to
        steps: Number of animation steps (higher = smoother)
        delay: Delay between frames in seconds
        from_image: Optional source image (uses current display if None)
        easing: Use cubic easing for smoother transitions
        fade_through_black: Fade out to black, then fade in from black
    """

    if steps <= 0:
        display.image(new_image)
        return

    if from_image is None:
        try:
            base = display.capture()
        except AttributeError:
            base = None
        if base is None:
            base = Image.new("RGB", new_image.size, (0, 0, 0))
    else:
        base = from_image

    base = base.convert("RGB")
    if base.size != new_image.size:
        base = base.resize(new_image.size, Image.ANTIALIAS)

    target = new_image.convert("RGB")

    if fade_through_black:
        # Fade out to black, then fade in from black
        black = Image.new("RGB", new_image.size, (0, 0, 0))
        half_steps = steps // 2

        # Fade out to black
        for i in range(half_steps + 1):
            t = i / half_steps
            alpha = _ease_in_out_cubic(t) if easing else t
            frame = Image.blend(base, black, alpha)
            display.image(frame)
            time.sleep(delay)

        # Fade in from black
        for i in range(half_steps + 1):
            t = i / half_steps
            alpha = _ease_in_out_cubic(t) if easing else t
            frame = Image.blend(black, target, alpha)
            display.image(frame)
            time.sleep(delay)
    else:
        # Direct cross-fade with optional easing
        for i in range(steps + 1):
            t = i / steps
            alpha = _ease_in_out_cubic(t) if easing else t
            frame = Image.blend(base, target, alpha)
            display.image(frame)
            time.sleep(delay)

@log_call
def animate_scroll(display: Display, image: Image.Image, speed=3, y_offset=None):
    """
    Scroll an image across the display.
    """
    if image is None:
        return

    bands = image.getbands() if hasattr(image, "getbands") else ()
    has_alpha = "A" in bands
    image = image.convert("RGBA" if has_alpha else "RGB")

    w, h = display.width, display.height
    img_w, img_h = image.size
    y = y_offset if y_offset is not None else (h - img_h) // 2
    direction = random.choice(("ltr", "rtl"))
    start, end, step = ((-img_w, w, speed) if direction == "ltr" else (w, -img_w, -speed))

    background_color = (0, 0, 0, 0) if has_alpha else (0, 0, 0)
    frame_mode = "RGBA" if has_alpha else "RGB"

    for x in range(start, end + step, step):
        frame = Image.new(frame_mode, (w, h), background_color)
        if has_alpha:
            frame.paste(image, (x, y), image)
            frame_to_show = frame.convert("RGB")
        else:
            frame.paste(image, (x, y))
            frame_to_show = frame
        display.image(frame_to_show)
        time.sleep(0.008)

    # Ensure the display is clear once the image has fully scrolled off-screen.
    final_frame = Image.new(frame_mode, (w, h), background_color)
    display.image(final_frame.convert("RGB") if has_alpha else final_frame)

# ─── Date & Time Helpers ─────────────────────────────────────────────────────
def parse_game_date(iso_date_str: str, time_str: str = "TBD") -> str:
    try:
        d = datetime.datetime.strptime(iso_date_str, "%Y-%m-%d").date()
    except Exception:
        return time_str
    today = datetime.datetime.now(CENTRAL_TIME).date()
    if d == today:
        day = "Today"
    elif d == today + datetime.timedelta(days=1):
        day = "Tomorrow"
    else:
        day = d.strftime("%a %-m/%-d")
    return f"{day} {time_str}" if time_str.upper() != "TBD" else f"{day} TBD"

def format_date_no_leading(dt_date: datetime.date) -> str:
    return f"{dt_date.month}/{dt_date.day}"

def format_time_no_leading(dt_time: datetime.time) -> str:
    return dt_time.strftime("%I:%M %p").lstrip("0")

def split_time_period(dt_time: datetime.time) -> tuple[str,str]:
    full = dt_time.strftime("%I:%M %p").lstrip("0")
    parts = full.rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts)==2 else (full, "")

# ─── Team & Standings Helpers ────────────────────────────────────────────────
def get_team_display_name(team) -> str:
    if not isinstance(team, dict):
        return str(team)
    t = team.get("team", team)
    for key in ("commonName","name","teamName","fullName","city"): 
        val = t.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return "UNK"

def get_opponent_last_game(team) -> str:
    if not isinstance(team, dict):
        return str(team)
    city = team.get("placeName", {}).get("default", "").strip()
    return city or get_team_display_name(team)

def extract_split_record(split_records: list, record_type: str) -> str:
    for sp in split_records:
        if sp.get("type", "").lower() == record_type.lower():
            w = sp.get("wins", "N/A")
            l = sp.get("losses", "N/A")
            p = sp.get("pct", "N/A")
            return f"{w}-{l} ({p})"
    return "N/A"

def wind_direction(degrees: float) -> str:
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSW","SW","WSW","W","WNW","NW","NNW"]
    try:
        idx = int((degrees / 22.5) + 0.5) % 16
        return dirs[idx]
    except Exception:
        return ""

wind_deg_to_compass = wind_direction

def center_coords(
    img_size: tuple[int,int],
    content_size: tuple[int,int],
    y_offset: int = 0
) -> tuple[int,int]:
    w, h = img_size
    cw, ch = content_size
    return ((w - cw)//2, (h - ch)//2 + y_offset)

# ─── MLB Abbreviations ────────────────────────────────────────────────────────
MLB_ABBREVIATIONS = {
    "Chicago Cubs": "CUBS", "Atlanta Braves": "ATL", "Miami Marlins": "MIA",
    # ... other teams ...
}

def get_mlb_abbreviation(team_name: str) -> str:
    return MLB_ABBREVIATIONS.get(team_name, team_name)


def next_game_from_schedule(schedule: List[Dict[str, Any]], today: Optional[datetime.date] = None) -> Optional[Dict[str, Any]]:
    today = today or datetime.date.today()

    def _game_no(entry: Dict[str, Any]) -> float:
        try:
            return float(entry.get("game_no", "0"))
        except Exception:
            return 0.0

    def _parse_game_date(raw: str) -> Optional[datetime.date]:
        if not raw:
            return None
        for fmt in ("%a, %b %d, %Y", "%a, %b %d"):
            try:
                parsed = datetime.datetime.strptime(raw, fmt)
                if fmt.endswith("%Y"):
                    return parsed.date()
                game_date = datetime.date(today.year, parsed.month, parsed.day)
                if game_date < today:
                    game_date = datetime.date(today.year + 1, parsed.month, parsed.day)
                return game_date
            except Exception:
                continue
        return None

    upcoming: List[tuple[datetime.date, float, Dict[str, Any]]] = []
    dated_games: List[tuple[datetime.date, float, Dict[str, Any]]] = []

    for entry in schedule:
        if entry.get("opponent") == "—":
            continue

        game_date = _parse_game_date(str(entry.get("date", "")).strip())
        if game_date is None:
            continue

        game_no = _game_no(entry)
        dated_games.append((game_date, game_no, entry))
        if game_date >= today:
            upcoming.append((game_date, game_no, entry))

    if upcoming:
        upcoming.sort(key=lambda item: (item[0], item[1]))
        return upcoming[0][2]

    last_game_no = max((game_no for _, game_no, _ in dated_games), default=0.0)
    fallback = [
        (game_no, entry)
        for entry in schedule
        if _game_no(entry) > last_game_no and entry.get("opponent") != "—"
    ]
    if fallback:
        fallback.sort(key=lambda item: item[0])
        return fallback[0][1]

    return None


_LOGO_BRIGHTNESS_OVERRIDES: dict[tuple[str, str], float] = {
    ("nhl", "WAS"): 1.35,
    ("nhl", "TBL"): 1.35,
    ("nhl", "TB"): 1.35,
    ("nfl", "NYJ"): 1.4,
    ("mlb", "SD"): 1.35,
    ("mlb", "DET"): 1.35,
    ("mlb", "NYY"): 1.35,
}


def _adjust_logo_brightness(logo: Image.Image, base_dir: str, abbr: str) -> Image.Image:
    sport = os.path.basename(os.path.normpath(base_dir or ""))
    key = (sport.lower(), (abbr or "").upper())
    factor = _LOGO_BRIGHTNESS_OVERRIDES.get(key)
    if not factor:
        return logo
    return ImageEnhance.Brightness(logo).enhance(factor)


def standard_next_game_logo_height(panel_height: int) -> int:
    """Return the shared next-game logo height used across team screens."""
    if panel_height <= 0:
        return 0

    try:
        from config import HEIGHT as CONFIG_HEIGHT, NEXT_GAME_LOGO_FONT_SIZE
    except Exception:
        CONFIG_HEIGHT = None
        NEXT_GAME_LOGO_FONT_SIZE = None

    if NEXT_GAME_LOGO_FONT_SIZE and CONFIG_HEIGHT:
        if panel_height == CONFIG_HEIGHT:
            return NEXT_GAME_LOGO_FONT_SIZE
        if CONFIG_HEIGHT > 0:
            scaled = int(round(NEXT_GAME_LOGO_FONT_SIZE * (panel_height / CONFIG_HEIGHT)))
            return max(1, scaled)

    if panel_height >= 128:
        return 375
    if panel_height >= 96:
        return 273
    return 223


def load_team_logo(base_dir: str, abbr: str, height: int = 90) -> Image.Image | None:
    filename = f"{abbr}.png"
    path = os.path.join(base_dir, filename)
    try:
        logo = Image.open(path).convert("RGBA")
        logo = _adjust_logo_brightness(logo, base_dir, abbr)
        ratio = height / logo.height
        return logo.resize((int(logo.width * ratio), height), Image.ANTIALIAS)
    except Exception as exc:
        logging.warning("Could not load logo '%s': %s", filename, exc)
        return None

@log_call
def colored_image(mono_img: Image.Image, screen_key: str) -> Image.Image:
    rgb = Image.new("RGB", mono_img.size, (0,0,0))
    pix = mono_img.load()
    draw = ImageDraw.Draw(rgb)
    col = random_color(screen_key)
    for y in range(mono_img.height):
        for x in range(mono_img.width):
            if pix[x, y]:
                draw.point((x, y), fill=col)
    return rgb

@log_call
def load_svg(key, url) -> Image.Image | None:
    cache_dir = os.path.join(os.path.dirname(__file__), "images", "nhl")
    os.makedirs(cache_dir, exist_ok=True)
    local = os.path.join(cache_dir, f"{key}.svg")
    if not os.path.exists(local):
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            with open(local, "wb") as f:
                f.write(r.content)
        except Exception as e:
            logging.warning(f"Failed to download NHL logo: {e}")
            return None
    try:
        from cairosvg import svg2png
        png = svg2png(url=local)
        return Image.open(BytesIO(png))
    except Exception:
        return None

# ─── GitHub Update Checker ─────────────────────────────────────────────────
class _GithubLedAnimator:
    """Hold the onboard LED at a barely visible blue glow."""

    def __init__(self, display: "Display") -> None:
        self._display = display
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def is_running_for(self, display: "Display") -> bool:
        return self._display is display and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=0.5)
        self._display.set_led(r=0.0, g=0.0, b=0.0)

    def _run(self) -> None:
        self._display.set_led(r=0.0, g=0.0, b=LED_INDICATOR_LEVEL)
        # Keep the LED steady until we're asked to stop.
        while not self._stop.wait(0.2):
            continue
        self._display.set_led(r=0.0, g=0.0, b=0.0)


def _start_github_led_animator(display: "Display") -> None:
    """Start the GitHub LED animator for the provided display."""

    global _GITHUB_LED_ANIMATOR

    animator = _GithubLedAnimator(display)
    _GITHUB_LED_ANIMATOR = animator
    try:  # pragma: no cover - hardware import
        animator.start()
    except Exception as exc:
        logging.debug("Failed to start GitHub LED animator: %s", exc)
        _GITHUB_LED_ANIMATOR = None


def _update_github_led(state: bool) -> None:
    """Reflect GitHub update status on the display LED."""

    global _GITHUB_LED_ANIMATOR, _GITHUB_LED_STATE

    _GITHUB_LED_STATE = state

    display = get_active_display()
    if display is None:
        if not state and _GITHUB_LED_ANIMATOR is not None:
            try:  # pragma: no cover - hardware import
                _GITHUB_LED_ANIMATOR.stop()
            except Exception as exc:
                logging.debug("Failed to stop GitHub LED animator without display: %s", exc)
            finally:
                _GITHUB_LED_ANIMATOR = None
        return

    if state:
        if _GITHUB_LED_ANIMATOR is not None:
            # Animator already running; nothing to change.
            if _GITHUB_LED_ANIMATOR.is_running_for(display):
                return
            # Display changed or thread stopped; ensure previous animator is stopped.
            try:
                _GITHUB_LED_ANIMATOR.stop()
            except Exception as exc:  # pragma: no cover - hardware import
                logging.debug("Failed to stop previous GitHub LED animator: %s", exc)
        _start_github_led_animator(display)
    else:
        if _GITHUB_LED_ANIMATOR is not None:
            try:
                _GITHUB_LED_ANIMATOR.stop()
            except Exception as exc:  # pragma: no cover - hardware import
                logging.debug("Failed to stop GitHub LED animator: %s", exc)
            finally:
                _GITHUB_LED_ANIMATOR = None


@contextmanager
def temporary_display_led(r: float, g: float, b: float):
    """Temporarily override the display LED, restoring GitHub status after."""

    global _GITHUB_LED_ANIMATOR

    display = get_active_display()
    if display is None:
        yield
        return

    animator = _GITHUB_LED_ANIMATOR
    if animator is not None and not animator.is_running_for(display):
        animator = None

    if animator is not None:
        try:  # pragma: no cover - hardware import
            animator.stop()
        except Exception as exc:
            logging.debug("Failed to stop GitHub LED animator before override: %s", exc)
        finally:
            _GITHUB_LED_ANIMATOR = None

    try:
        display.set_led(r=r, g=g, b=b)
        yield
    finally:
        if _GITHUB_LED_STATE:
            _start_github_led_animator(display)
        else:
            try:
                display.set_led(r=0.0, g=0.0, b=0.0)
            except Exception as exc:
                logging.debug("Failed to reset LED after override: %s", exc)

def check_github_updates() -> bool:
    """
    Return True if the local branch differs from its upstream tracking branch.
    Also logs the list of files that have changed on the remote.

    Safe fallbacks:
      - Handles non-git directories gracefully.
      - Skips detached HEADs or branches without an upstream.
      - Silently returns False if remote can't be fetched.
    """
    repo_dir = os.path.dirname(__file__)

    # Is this a git repo?
    try:
        subprocess.check_call(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        logging.info("check_github_updates: not a git repository, skipping check")
        return False

    # Local branch name (skip detached HEADs)
    try:
        local_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        logging.exception("check_github_updates: failed to determine local branch")
        return False

    if local_branch in {"HEAD", ""}:
        logging.info("check_github_updates: detached HEAD, skipping check")
        return False

    # Local SHA
    try:
        local_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        logging.exception("check_github_updates: failed to read local HEAD")
        return False

    # Upstream branch for the current branch
    try:
        upstream_ref = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        logging.info(
            "check_github_updates: no upstream tracking branch for %s, skipping check",
            local_branch,
        )
        return False

    # Fetch remote so we can diff against it
    try:
        subprocess.check_call(
            ["git", "fetch", "--quiet", "origin"],
            cwd=repo_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        logging.warning("check_github_updates: failed to fetch from origin")
        return False

    # Remote SHA for the upstream branch
    try:
        remote_sha = subprocess.check_output(
            ["git", "rev-parse", upstream_ref],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        logging.warning(
            "check_github_updates: failed to resolve upstream %s for %s",
            upstream_ref,
            local_branch,
        )
        return False

    updated = (local_sha != remote_sha)
    logging.info(f"check_github_updates: updates available = {updated}")
    _update_github_led(updated)

    # If updated, log which files changed
    if updated:
        try:
            changed = subprocess.check_output(
                ["git", "diff", "--name-only", f"{local_sha}..{remote_sha}"],
                cwd=repo_dir,
            ).decode().splitlines()

            if not changed:
                logging.info("check_github_updates: no file list available (empty diff?)")
            else:
                # Keep the log readable if there are many files
                MAX_LIST = 100
                shown = changed[:MAX_LIST]
                logging.info(
                    f"check_github_updates: {len(changed)} file(s) differ from {upstream_ref}:"
                )
                for p in shown:
                    logging.info(f"  • {p}")
                if len(changed) > MAX_LIST:
                    logging.info(f"  …and {len(changed) - MAX_LIST} more")
        except Exception:
            logging.exception("check_github_updates: failed to list changed files")

    return updated

MLB_ABBREVIATIONS = {
    "Chicago Cubs": "CUBS", "Cubs": "CUBS",
    "Atlanta Braves": "ATL", "Braves": "ATL",
    "Miami Marlins": "MIA", "Marlins": "MIA",
    "New York Mets": "NYM", "Mets": "NYM",
    "Philadelphia Phillies": "PHI", "Phillies": "PHI",
    "Washington Nationals": "WAS", "Nationals": "WAS",
    "Cincinnati Reds": "CIN", "Reds": "CIN",
    "Milwaukee Brewers": "MIL", "Brewers": "MIL",
    "Pittsburgh Pirates": "PIT", "Pirates": "PIT",
    "St. Louis Cardinals": "STL", "Cardinals": "STL",
    "Arizona Diamondbacks": "ARI", "Diamondbacks": "ARI",
    "Colorado Rockies": "COL", "Rockies": "COL",
    "Los Angeles Dodgers": "LAD", "Dodgers": "LAD",
    "San Diego Padres": "SD", "Padres": "SD",
    "San Francisco Giants": "SF", "Giants": "SF",
    "Baltimore Orioles": "BAL", "Orioles": "BAL",
    "Boston Red Sox": "BOS", "Red Sox": "BOS",
    "New York Yankees": "NYY", "Yankees": "NYY",
    "Tampa Bay Rays": "TB", "Rays": "TB",
    "Toronto Blue Jays": "TOR", "Blue Jays": "TOR",
    "Chicago White Sox": "SOX", "White Sox": "SOX",
    "Cleveland Guardians": "CLE", "Guardians": "CLE",
    "Detroit Tigers": "DET", "Tigers": "DET",
    "Kansas City Royals": "KC", "Royals": "KC",
    "Minnesota Twins": "MIN", "Twins": "MIN",
    "Houston Astros": "HOU", "Astros": "HOU",
    "Los Angeles Angels": "LAA", "Angels": "LAA",
    "Athletics": "ATH",
    "Seattle Mariners": "SEA", "Mariners": "SEA",
    "Texas Rangers": "TEX", "Rangers": "TEX",
}

def get_mlb_abbreviation(team_name: str) -> str:
    return MLB_ABBREVIATIONS.get(team_name, team_name)

# ─── Weather helpers ──────────────────────────────────────────────────────────
_WEATHER_ICON_DIR = Path(__file__).resolve().parent / "images" / "WeatherKit"
_WEATHER_ICON_FILENAME_MAP: dict[str, str] = {
    "blizzard": "Blizzard.png",
    "blowingsnow": "Snow.png",
    "breezy": "Windy.png",
    "clear": "Clear.png",
    "cloudy": "Cloudy.png",
    "drizzle": "Rain.png",
    "dust": "Haze.png",
    "extreme": "Clear.png",
    "flurries": "Snow.png",
    "fog": "Fog.png",
    "freezingdrizzle": "Rain.png",
    "freezingrain": "Rain.png",
    "frigid": "Clear.png",
    "hail": "Hail.png",
    "haze": "Haze.png",
    "heavyrain": "HeavyRain.png",
    "heavysnow": "HeavySnow.png",
    "hot": "Clear.png",
    "hurricane": "Thunderstorms.png",
    "isolatedthunderstorms": "Thunderstorms.png",
    "mostlyclear": "MostlyClear.png",
    "mostlycloudy": "Cloudy.png",
    "partlycloudy": "PartlyCloudy.png",
    "rain": "Rain.png",
    "rainheavy": "HeavyRain.png",
    "scatteredthunderstorms": "Thunderstorms.png",
    "sleet": "Sleet.png",
    "smoke": "Haze.png",
    "snow": "Snow.png",
    "snowheavy": "HeavySnow.png",
    "strongstorms": "Thunderstorms.png",
    "sunflurries": "Snow.png",
    "sunshowers": "Rain.png",
    "thunder": "Thunderstorms.png",
    "thunderstorms": "Thunderstorms.png",
    "tornado": "Thunderstorms.png",
    "wind": "Windy.png",
    "windy": "Windy.png",
}
_WEATHER_ICON_NIGHT_OVERRIDES: dict[str, str] = {
    "Clear.png": "Clear_night.png",
    "MostlyClear.png": "MostlyClear_night.png",
    "PartlyCloudy.png": "PartlyCloudy_night.png",
}

_WEATHER_ICON_CACHE: dict[tuple[str, int], Image.Image | None] = {}


def _normalize_weather_icon_key(icon_code: str) -> Optional[str]:
    if not icon_code:
        return None
    key = str(icon_code).strip().lower()
    if not key:
        return None

    for prefix in ("wk-",):
        if key.startswith(prefix):
            key = key[len(prefix) :]
            break

    for suffix in ("-day", "-night"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
            break

    return key.replace("_", "").replace("-", "").replace(" ", "")


def _load_weatherkit_icon(icon_code: str, size: int) -> Image.Image | None:
    normalized = _normalize_weather_icon_key(icon_code)
    if not normalized:
        return None

    is_night = isinstance(icon_code, str) and icon_code.strip().lower().endswith("-night")

    filename = _WEATHER_ICON_FILENAME_MAP.get(normalized)
    if not filename:
        return None

    if is_night:
        filename = _WEATHER_ICON_NIGHT_OVERRIDES.get(filename, filename)

    path = _WEATHER_ICON_DIR / filename
    if not path.exists():
        logging.warning("Weather icon %s not found at %s", icon_code, path)
        return None

    try:
        icon = Image.open(path).convert("RGBA")
        if icon.height != size:
            ratio = size / float(icon.height)
            icon = icon.resize((max(1, int(round(icon.width * ratio))), size), Image.ANTIALIAS)
        return icon
    except Exception as exc:  # pragma: no cover - image loading varies
        logging.warning("Weather icon load failed for %s: %s", icon_code, exc)
        return None


def _render_weather_icon_placeholder(icon_code: str, size: int) -> Image.Image | None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    palette = [
        (255, 223, 99),
        (129, 199, 212),
        (255, 179, 71),
        (176, 196, 222),
        (255, 140, 105),
        (152, 251, 152),
        (221, 160, 221),
    ]
    color = palette[hash(icon_code) % len(palette)]

    inset = max(2, size // 12)
    draw.rounded_rectangle(
        [(inset, inset), (size - inset, size - inset)],
        radius=size // 5,
        fill=(0, 0, 0, 180),
    )
    circle_radius = size // 3
    center = (size // 2, size // 2)
    draw.ellipse(
        [
            (center[0] - circle_radius, center[1] - circle_radius),
            (center[0] + circle_radius, center[1] + circle_radius),
        ],
        fill=color + (220,),
    )

    label = (icon_code.replace("wk-", "").replace("-", " ") or "?").split()[0]
    font_size = max(12, size // 4)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except Exception:  # pragma: no cover - font availability varies
        font = ImageFont.load_default()
    text = label[:3].upper()
    text_w, text_h = draw.textsize(text, font=font)
    draw.text(
        ((size - text_w) // 2, (size - text_h) // 2),
        text,
        font=font,
        fill=(0, 0, 0),
    )

    return img


@log_call
def fetch_weather_icon(icon_code: str, size: int) -> Image.Image | None:
    if not icon_code:
        return None

    cache_key = (icon_code, size)
    if cache_key in _WEATHER_ICON_CACHE:
        return _WEATHER_ICON_CACHE[cache_key]

    icon = _load_weatherkit_icon(icon_code, size)
    if icon is None:
        try:
            icon = _render_weather_icon_placeholder(icon_code, size)
        except Exception as exc:  # pragma: no cover - drawing failures are non-fatal
            logging.warning("Weather icon render failed: %s", exc)
            icon = None

    _WEATHER_ICON_CACHE[cache_key] = icon
    return icon


def uv_index_color(uvi: int) -> tuple[int, int, int]:
    if uvi <= 1:
        return (0, 255, 0)
    if uvi == 2:
        return (200, 120, 255)
    if 3 <= uvi <= 5:
        return (255, 255, 0)
    if 6 <= uvi <= 7:
        return (255, 165, 0)
    if 8 <= uvi <= 10:
        return (255, 0, 0)
    return (128, 0, 128)


def timestamp_to_datetime(value, tz) -> datetime.datetime | None:
    try:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None

            if text.isdigit():
                value = float(text)
            else:
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                dt = datetime.datetime.fromisoformat(text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                return dt.astimezone(tz)

        return datetime.datetime.fromtimestamp(value, tz)
    except Exception:
        return None


def bright_color(min_luma: int = 160) -> tuple[int, int, int]:
    for _ in range(20):
        r = random.randint(80, 255)
        g = random.randint(80, 255)
        b = random.randint(80, 255)
        luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if luma >= min_luma:
            return (r, g, b)
    return (255, 255, 255)


_GH_ICON_CACHE: dict[tuple[int, bool, tuple[str, ...]], Image.Image | None] = {}


def load_github_icon(size: int, invert: bool, paths: list[str]) -> Image.Image | None:
    key = (size, bool(invert), tuple(paths))
    if key in _GH_ICON_CACHE:
        return _GH_ICON_CACHE[key]

    path = next((p for p in paths if os.path.exists(p)), None)
    if not path:
        _GH_ICON_CACHE[key] = None
        return None

    try:
        icon = Image.open(path).convert("RGBA")
        if icon.height != size:
            ratio = size / float(icon.height)
            icon = icon.resize((max(1, int(round(icon.width * ratio))), size), Image.ANTIALIAS)

        if invert:
            r, g, b, a = icon.split()
            rgb_inv = ImageOps.invert(Image.merge("RGB", (r, g, b)))
            icon = Image.merge("RGBA", (*rgb_inv.split(), a))

        _GH_ICON_CACHE[key] = icon
        return icon
    except Exception:
        _GH_ICON_CACHE[key] = None
        return None


def time_strings(now: datetime.datetime) -> tuple[str, str]:
    time_str = now.strftime("%-I:%M")
    am_pm = now.strftime("%p")
    if time_str.startswith("0"):
        time_str = time_str[1:]
    return time_str, am_pm


def date_strings(now: datetime.datetime) -> tuple[str, str]:
    weekday = now.strftime("%A")
    return weekday, f"{now.strftime('%B')} {now.day}, {now.year}"


def decode_html(text: str) -> str:
    try:
        return html.unescape(text)
    except Exception:
        return text


def fetch_directions_routes(
    origin: str,
    destination: str,
    api_key: str,
    *,
    avoid_highways: bool = False,
    url: str,
) -> List[Dict[str, Any]]:
    if not api_key:
        logging.warning("Travel: no GOOGLE_MAPS_API_KEY configured.")
        return []

    params = {
        "origin": origin,
        "destination": destination,
        "alternatives": "true",
        "departure_time": "now",
        "traffic_model": "best_guess",
        "region": "us",
        "key": api_key,
    }
    if avoid_highways:
        params["avoid"] = "highways"

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logging.warning("Directions request failed: %s", exc)
        return []

    if payload.get("status") != "OK":
        logging.warning(
            "Directions status=%s, error_message=%s",
            payload.get("status"),
            payload.get("error_message"),
        )
        return []

    routes = payload.get("routes", []) or []
    for route in routes:
        leg = (route.get("legs") or [{}])[0]
        route["_summary"] = decode_html(route.get("summary", "")).lower()
        duration = leg.get("duration_in_traffic") or leg.get("duration") or {}
        route["_duration_text"] = duration.get("text", "")
        route["_duration_sec"] = duration.get("value", 0)
        steps = leg.get("steps", []) or []
        fragments = []
        for step in steps:
            instruction = decode_html(step.get("html_instructions", "")).lower()
            fragments.append(instruction)
        route["_steps_text"] = " ".join(fragments)
    return routes


def route_contains(route: Dict[str, Any], token: str) -> bool:
    token = token.lower()
    return token in route.get("_summary", "") or token in route.get("_steps_text", "")


def choose_route_by_token(routes: List[Dict[str, Any]], token: str) -> Optional[Dict[str, Any]]:
    for route in routes:
        if route_contains(route, token):
            return route
    return None


def choose_route_by_any(routes: List[Dict[str, Any]], tokens: List[str]) -> Optional[Dict[str, Any]]:
    for token in tokens:
        match = choose_route_by_token(routes, token)
        if match:
            return match
    return None


def format_duration_text(route: Optional[Dict[str, Any]]) -> str:
    if not route:
        return "N/A"
    text = route.get("_duration_text") or ""
    return text if text else "N/A"


def fastest_route(routes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not routes:
        return None
    return min(routes, key=lambda r: r.get("_duration_sec", math.inf))


# ─── Backlight brightness control ─────────────────────────────────────────────
_BACKLIGHT_PATH = None
_BACKLIGHT_MAX_BRIGHTNESS = None
_CURRENT_BRIGHTNESS_STATE = None  # None, 0, or 100


def _find_backlight_device() -> Optional[str]:
    """Find the backlight device path."""
    backlight_base = "/sys/class/backlight"
    try:
        if not os.path.isdir(backlight_base):
            return None
        devices = os.listdir(backlight_base)
        if not devices:
            return None
        # Prefer specific device names for HyperPixel
        for preferred in ["rpi_backlight", "10-0045"]:
            if preferred in devices:
                return os.path.join(backlight_base, preferred)
        # Fall back to first available device
        return os.path.join(backlight_base, devices[0])
    except Exception as exc:
        logging.debug("Failed to find backlight device: %s", exc)
        return None


def _get_max_brightness() -> Optional[int]:
    """Get the maximum brightness value for the backlight."""
    global _BACKLIGHT_PATH, _BACKLIGHT_MAX_BRIGHTNESS

    if _BACKLIGHT_MAX_BRIGHTNESS is not None:
        return _BACKLIGHT_MAX_BRIGHTNESS

    if _BACKLIGHT_PATH is None:
        _BACKLIGHT_PATH = _find_backlight_device()

    if _BACKLIGHT_PATH is None:
        return None

    max_brightness_file = os.path.join(_BACKLIGHT_PATH, "max_brightness")
    try:
        with open(max_brightness_file, "r") as f:
            _BACKLIGHT_MAX_BRIGHTNESS = int(f.read().strip())
            return _BACKLIGHT_MAX_BRIGHTNESS
    except Exception as exc:
        logging.debug("Failed to read max_brightness: %s", exc)
        return None


def set_brightness(percent: int) -> bool:
    """Set the backlight brightness to a percentage (0-100).

    Returns True if successful, False otherwise.
    """
    global _BACKLIGHT_PATH, _CURRENT_BRIGHTNESS_STATE

    if _BACKLIGHT_PATH is None:
        _BACKLIGHT_PATH = _find_backlight_device()

    if _BACKLIGHT_PATH is None:
        logging.debug("No backlight device found")
        return False

    max_brightness = _get_max_brightness()
    if max_brightness is None:
        logging.debug("Could not determine max brightness")
        return False

    # Clamp percent to 0-100
    percent = max(0, min(100, percent))

    # Calculate the actual brightness value
    brightness_value = int((percent / 100.0) * max_brightness)

    brightness_file = os.path.join(_BACKLIGHT_PATH, "brightness")
    try:
        with open(brightness_file, "w") as f:
            f.write(str(brightness_value))
        _CURRENT_BRIGHTNESS_STATE = percent
        logging.info("🔆 Brightness set to %d%%", percent)
        return True
    except Exception as exc:
        logging.warning("Failed to set brightness: %s", exc)
        return False


def get_brightness() -> Optional[int]:
    """Get the current backlight brightness as a percentage (0-100).

    Returns None if unable to read brightness.
    """
    global _BACKLIGHT_PATH

    if _BACKLIGHT_PATH is None:
        _BACKLIGHT_PATH = _find_backlight_device()

    if _BACKLIGHT_PATH is None:
        return None

    max_brightness = _get_max_brightness()
    if max_brightness is None:
        return None

    brightness_file = os.path.join(_BACKLIGHT_PATH, "brightness")
    try:
        with open(brightness_file, "r") as f:
            current = int(f.read().strip())
        percent = int((current / max_brightness) * 100)
        return percent
    except Exception as exc:
        logging.debug("Failed to read brightness: %s", exc)
        return None


def toggle_brightness() -> bool:
    """Toggle brightness between 0% and 100%.

    Returns True if successful, False otherwise.
    """
    global _CURRENT_BRIGHTNESS_STATE

    # Get current brightness
    current = get_brightness()
    if current is None:
        # If we can't read current brightness, try to use cached state
        current = _CURRENT_BRIGHTNESS_STATE

    # If still unknown, default to assuming it's at 100%
    if current is None:
        current = 100

    # Toggle: if current is near 0, go to 100; otherwise go to 0
    if current <= 10:
        return set_brightness(100)
    else:
        return set_brightness(0)
