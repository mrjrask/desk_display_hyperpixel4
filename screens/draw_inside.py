#!/usr/bin/env python3
"""
draw_inside.py (RGB)
Optimized for:
  • HyperPixel 4.0 Square: 720 x 720
  • HyperPixel 4.0/4.3 (landscape): 800 x 480

Universal environmental sensor screen with a calmer, data-forward layout:
  • Title area with automatic sensor attribution
  • Soft temperature card with contextual descriptor
  • Responsive grid of metric cards driven entirely by the available readings
Everything is dynamically sized from config.WIDTH/HEIGHT, so it adapts to square
(720x720) and wide (800x480) canvases without code changes.
"""

from __future__ import annotations
import time
import logging
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from PIL import Image, ImageDraw
import config
from utils import (
    clear_display,
    clone_font,
    fit_font,
    format_voc_ohms,
    measure_text,
    temperature_color,
)

# Use the HyperPixel-friendly sensor mux (bus-number based; honors INSIDE_SENSOR_I2C_BUS)
from inside_sensor import read_all as read_all_sensors

W, H = config.WIDTH, config.HEIGHT

SensorReadings = Dict[str, Optional[float]]
SensorProbeResult = Tuple[str, Callable[[], SensorReadings]]

# ── Shared helpers ───────────────────────────────────────────────────────────

def _extract_field(data: Any, key: str) -> Optional[float]:
    if hasattr(data, key):
        value = getattr(data, key)
    elif isinstance(data, dict):
        value = data.get(key)
    else:
        value = None
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None

def _mix_color(color: Tuple[int, int, int], target: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    factor = max(0.0, min(1.0, factor))
    return tuple(int(round(color[idx] * (1 - factor) + target[idx] * factor)) for idx in range(3))

# ── Sensor probe (replaced with inside_sensor) ───────────────────────────────
def _probe_sensor() -> Tuple[Optional[str], Optional[Callable[[], SensorReadings]]]:
    """
    Use inside_sensor.read_all() to access sensors on the correct Linux I2C bus
    (e.g., /dev/i2c-15 for HyperPixel Square breakout). Map into our
    existing SensorReadings shape:
      temp_f, humidity, pressure_inhg, voc_ohms
    Returns (provider_label, reader_callable) or (None, None) if unavailable.
    """
    blob = read_all_sensors()
    if blob.get("error"):
        logging.warning("No supported indoor environmental sensor detected.")
        return None, None

    sensors = blob.get("sensors", {})
    env = sensors.get("env_primary") or {}  # BME68x/680/280 if available
    sht = sensors.get("sht4x") or {}        # for humidity fallback

    provider = env.get("sensor_model") or sht.get("sensor_model") or "Unknown"
    logging.info("draw_inside: detected %s on I2C bus %s", provider, blob.get("bus"))

    def _reader() -> SensorReadings:
        t_c = _extract_field(env, "temperature_c")
        h   = _extract_field(env, "humidity_percent")
        p_h = _extract_field(env, "pressure_hpa")
        g   = _extract_field(env, "gas_ohms")

        # If env has no humidity, try SHT4x fallback
        if h is None and sht:
            h = _extract_field(sht, "humidity_percent")

        temp_f = t_c * 9.0 / 5.0 + 32.0 if t_c is not None else None
        pressure_inhg = p_h * 0.02953 if p_h is not None else None

        return dict(
            temp_f=temp_f,
            humidity=h,
            pressure_inhg=pressure_inhg,
            voc_ohms=g,
        )

    return provider, _reader

# ── Layout + drawing helpers ─────────────────────────────────────────────────

def _draw_temperature_panel(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    rect: Tuple[int, int, int, int],
    temp_f: float,
    temp_text: str,
    descriptor: str,
    temp_base,
    label_base,
) -> None:
    x0, y0, x1, y1 = rect
    color = temperature_color(temp_f)
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)

    radius = max(14, min(26, min(width, height) // 5))
    bg = _mix_color(color, config.INSIDE_COL_BG, 0.4)
    outline = _mix_color(color, config.INSIDE_COL_BG, 0.25)
    draw.rounded_rectangle(rect, radius=radius, fill=bg, outline=outline, width=1)

    padding_x = max(16, width // 12)
    padding_y = max(12, height // 10)
    label_text = "Temperature"

    label_base_size = getattr(label_base, "size", 18)
    label_font = fit_font(
        draw,
        label_text,
        label_base,
        max_width=width - 2 * padding_x,
        max_height=max(14, int(height * 0.18)),
        min_pt=min(label_base_size, 10),
        max_pt=label_base_size,
    )
    _, label_h = measure_text(draw, label_text, label_font)
    label_x = x0 + padding_x
    label_y = y0 + padding_y

    descriptor = descriptor.strip()
    has_descriptor = bool(descriptor)
    if has_descriptor:
        descriptor_base_size = getattr(label_base, "size", 18)
        desc_font = fit_font(
            draw,
            descriptor,
            label_base,
            max_width=width - 2 * padding_x,
            max_height=max(14, int(height * 0.2)),
            min_pt=min(descriptor_base_size, 12),
            max_pt=descriptor_base_size,
        )
        _, desc_h = measure_text(draw, descriptor, desc_font)
        desc_x = x0 + padding_x
        desc_y = y1 - padding_y - desc_h
    else:
        desc_font = None
        desc_h = 0
        desc_x = x0 + padding_x
        desc_y = y1 - padding_y

    value_gap = max(10, height // 14)
    value_top = label_y + label_h + value_gap
    value_bottom = desc_y - value_gap if has_descriptor else y1 - padding_y
    value_max_height = max(32, value_bottom - value_top)
    temp_base_size = getattr(temp_base, "size", 48)

    safe_margin = max(4, width // 28)
    inner_left = x0 + padding_x
    inner_right = x1 - padding_x - safe_margin
    if inner_right <= inner_left:
        safe_margin = max(0, (width - 2 * padding_x - 1) // 2)
        inner_left = x0 + padding_x + safe_margin
        inner_right = max(inner_left + 1, x1 - padding_x - safe_margin)

    value_region_width = max(1, inner_right - inner_left)

    temp_font = fit_font(
        draw,
        temp_text,
        temp_base,
        max_width=value_region_width,
        max_height=value_max_height,
        min_pt=min(temp_base_size, 20),
        max_pt=temp_base_size,
    )

    temp_bbox = draw.textbbox((0, 0), temp_text, font=temp_font)
    temp_w = temp_bbox[2] - temp_bbox[0]
    temp_h = temp_bbox[3] - temp_bbox[1]
    while temp_w > value_region_width and getattr(temp_font, "size", 0) > 12:
        next_size = getattr(temp_font, "size", 0) - 1
        temp_font = clone_font(temp_base, next_size)
        temp_bbox = draw.textbbox((0, 0), temp_text, font=temp_font)
        temp_w = temp_bbox[2] - temp_bbox[0]
        temp_h = temp_bbox[3] - temp_bbox[1]

    temp_x = inner_left
    temp_y = value_top

    if has_descriptor:
        if temp_y + temp_h > desc_y - value_gap:
            temp_y = max(label_y + label_h + value_gap, desc_y - value_gap - temp_h)
    else:
        max_temp_y = y1 - padding_y - temp_h
        if temp_y > max_temp_y:
            temp_y = max_temp_y

    draw.text(
        (label_x, label_y),
        label_text,
        font=label_font,
        fill=_mix_color(color, config.INSIDE_COL_TEXT, 0.2),
    )
    draw.text((temp_x, temp_y), temp_text, font=temp_font, fill=config.INSIDE_COL_TEXT)
    if has_descriptor:
        draw.text(
            (desc_x, desc_y),
            descriptor,
            font=desc_font,
            fill=_mix_color(color, config.INSIDE_COL_TEXT, 0.35),
        )

def _draw_metric_row(
    draw: ImageDraw.ImageDraw,
    rect: Tuple[int, int, int, int],
    label: str,
    value: str,
    accent: Tuple[int, int, int],
    label_base,
    value_base,
) -> None:
    x0, y0, x1, y1 = rect
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    radius = max(8, min(20, min(width, height) // 4))
    bg = _mix_color(accent, config.INSIDE_COL_BG, 0.3)
    outline = _mix_color(accent, config.INSIDE_COL_BG, 0.18)
    draw.rounded_rectangle(rect, radius=radius, fill=bg, outline=outline, width=1)

    padding_x = max(10, width // 10)
    padding_y = max(6, height // 8)

    available_width = max(1, width - 2 * padding_x)
    available_height = max(1, height - 2 * padding_y)

    label_base_size = getattr(label_base, "size", 18)
    label_min_pt = min(label_base_size, 8 if width < 120 else 10)
    label_font = fit_font(
        draw,
        label,
        label_base,
        max_width=available_width,
        max_height=max(12, int(height * 0.38)),
        min_pt=label_min_pt,
        max_pt=label_base_size,
    )
    label_w, label_h = measure_text(draw, label, label_font)

    value_base_size = getattr(value_base, "size", 24)
    value_min_pt = min(value_base_size, 10 if width < 120 else 12)
    value_max_height = max(18, available_height - label_h - max(6, height // 12))
    value_font = fit_font(
        draw,
        value,
        value_base,
        max_width=available_width,
        max_height=value_max_height,
        min_pt=value_min_pt,
        max_pt=value_base_size,
    )
    value_w, value_h = measure_text(draw, value, value_font)

    def _shrink_font(
        text: str,
        base,
        current,
        current_size: int,
        min_size: int,
    ) -> Tuple[Any, Tuple[int, int], int]:
        width_limit = available_width
        height_limit = available_height
        width, height = measure_text(draw, text, current)
        while (width > width_limit or height > height_limit) and current_size > min_size:
            next_size = current_size - 1
            new_font = clone_font(base, next_size)
            new_size = getattr(new_font, "size", current_size)
            if new_size >= current_size:
                break
            current = new_font
            current_size = new_size
            width, height = measure_text(draw, text, current)
        return current, (width, height), current_size

    label_size = getattr(label_font, "size", label_base_size)
    value_size = getattr(value_font, "size", value_base_size)

    label_font, (label_w, label_h), label_size = _shrink_font(
        label,
        label_base,
        label_font,
        label_size,
        label_min_pt,
    )

    value_font, (value_w, value_h), value_size = _shrink_font(
        value,
        value_base,
        value_font,
        value_size,
        value_min_pt,
    )

    min_gap = max(6, height // 12)
    total_needed = label_h + min_gap + value_h
    while total_needed > available_height and (label_size > label_min_pt or value_size > value_min_pt):
        shrink_label = label_h >= value_h or value_size <= value_min_pt
        if shrink_label and label_size > label_min_pt:
            next_size = max(label_min_pt, label_size - 1)
            label_font = clone_font(label_base, next_size)
            label_size = getattr(label_font, "size", label_size - 1)
            label_w, label_h = measure_text(draw, label, label_font)
        elif value_size > value_min_pt:
            next_size = max(value_min_pt, value_size - 1)
            value_font = clone_font(value_base, next_size)
            value_size = getattr(value_font, "size", value_size - 1)
            value_w, value_h = measure_text(draw, value, value_font)
        else:
            break
        total_needed = label_h + min_gap + value_h

    label_w = min(label_w, available_width)
    value_w = min(value_w, available_width)

    label_x = x0 + padding_x
    label_y = y0 + padding_y
    value_x = x0 + padding_x
    value_y = y1 - padding_y - value_h
    if value_y - (label_y + label_h) < min_gap:
        value_y = min(y1 - padding_y - value_h, label_y + label_h + min_gap)

    label_color = _mix_color(accent, config.INSIDE_COL_TEXT, 0.25)
    value_color = config.INSIDE_COL_TEXT

    draw.text((label_x, label_y), label, font=label_font, fill=label_color)
    draw.text((value_x, value_y), value, font=value_font, fill=value_color)

def _metric_grid_dimensions(count: int, is_square: bool) -> Tuple[int, int]:
    if count <= 0:
        return 0, 0
    if is_square:
        if count <= 2:
            columns = count
        elif count <= 6:
            columns = 2
        else:
            columns = 3
    else:
        if count <= 3:
            columns = count
        elif count <= 8:
            columns = 3
        else:
            columns = 4
    columns = max(1, columns)
    rows = int(math.ceil(count / columns))
    return columns, rows

def _draw_metric_rows(
    draw: ImageDraw.ImageDraw,
    rect: Tuple[int, int, int, int],
    metrics: Sequence[Dict[str, Any]],
    label_base,
    value_base,
    is_square: bool,
) -> None:
    x0, y0, x1, y1 = rect
    count = len(metrics)
    width = max(0, x1 - x0)
    height = max(0, y1 - y0)
    if count <= 0 or width <= 0 or height <= 0:
        return

    columns, rows = _metric_grid_dimensions(count, is_square)
    if columns <= 0 or rows <= 0:
        return

    if columns > 1:
        desired_h_gap = max(8, width // (30 if is_square else 40))
        max_h_gap = max(0, (width - columns) // (columns - 1))
        h_gap = min(desired_h_gap, max_h_gap)
    else:
        h_gap = 0
    if rows > 1:
        desired_v_gap = max(8, height // (30 if is_square else 28))
        max_v_gap = max(0, (height - rows) // (rows - 1))
        v_gap = min(desired_v_gap, max_v_gap)
    else:
        v_gap = 0

    total_h_gap = h_gap * (columns - 1)
    total_v_gap = v_gap * (rows - 1)

    available_width = max(columns, width - total_h_gap)
    available_height = max(rows, height - total_v_gap)

    cell_width = max(72, available_width // columns)
    if cell_width * columns + total_h_gap > width:
        cell_width = max(1, available_width // columns)
    cell_height = max(44, available_height // rows)
    if cell_height * rows + total_v_gap > height:
        cell_height = max(1, available_height // rows)

    grid_width = min(width, cell_width * columns + total_h_gap)
    grid_height = min(height, cell_height * rows + total_v_gap)
    start_x = x0 + max(0, (width - grid_width) // 2)
    start_y = y0 + max(0, (height - grid_height) // 2)

    for index, metric in enumerate(metrics):
        row = index // columns
        col = index % columns
        left = start_x + col * (cell_width + h_gap)
        top = start_y + row * (cell_height + v_gap)
        right = min(x1, left + cell_width)
        bottom = min(y1, top + cell_height)
        if right <= left or bottom <= top:
            continue
        _draw_metric_row(
            draw,
            (left, top, right, bottom),
            metric["label"],
            metric["value"],
            metric["color"],
            label_base,
            value_base,
        )

def _prettify_metric_label(key: str) -> str:
    key = key.replace("_", " ").strip()
    if not key:
        return "Value"
    replacements = {
        "voc": "VOC",
        "co2": "CO₂",
        "co": "CO",
        "pm25": "PM2.5",
        "pm10": "PM10",
        "iaq": "IAQ",
    }
    parts = []
    for token in key.split():
        lower = token.lower()
        if lower in replacements:
            parts.append(replacements[lower])
        elif len(token) <= 2:
            parts.append(token.upper())
        else:
            parts.append(token.capitalize())
    return " ".join(parts)

def _format_generic_metric_value(key: str, value: float) -> str:
    key_lower = key.lower()
    if key_lower.endswith("_ohms"):
        return format_voc_ohms(value)
    if key_lower.endswith("_f"):
        return f"{value:.1f}°F"
    if key_lower.endswith("_c"):
        return f"{value:.1f}°C"
    if key_lower.endswith("_ppm"):
        return f"{value:.0f} ppm"
    if key_lower.endswith("_ppb"):
        return f"{value:.0f} ppb"
    if key_lower.endswith("_percent") or key_lower.endswith("_pct"):
        return f"{value:.1f}%"
    if key_lower.endswith("_inhg"):
        return f"{value:.2f} inHg"
    if key_lower.endswith("_hpa"):
        return f"{value:.1f} hPa"
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.0f}"
    if magnitude >= 100:
        return f"{value:.0f}"
    if magnitude >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"

# ── Main render ──────────────────────────────────────────────────────────────
def _clean_metric(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except Exception:
        return None
    if not math.isfinite(numeric):
        return None
    return numeric

def _build_metric_entries(data: Dict[str, Optional[float]]) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    used_keys: Set[str] = set()
    used_groups: Set[str] = set()

    palette: List[Tuple[int, int, int]] = [
        config.INSIDE_CHIP_BLUE,
        config.INSIDE_CHIP_AMBER,
        config.INSIDE_CHIP_PURPLE,
        _mix_color(config.INSIDE_CHIP_BLUE, config.INSIDE_CHIP_AMBER, 0.45),
        _mix_color(config.INSIDE_CHIP_PURPLE, config.INSIDE_CHIP_BLUE, 0.4),
        _mix_color(config.INSIDE_CHIP_PURPLE, config.INSIDE_COL_BG, 0.35),
    ]

    Spec = Tuple[str, str, Callable[[float], str], Tuple[int, int, int], Optional[str]]
    known_specs: Sequence[Spec] = (
        ("humidity", "Humidity", lambda v: f"{v:.1f}%", config.INSIDE_CHIP_BLUE, "humidity"),
        ("dew_point_f", "Dew Point", lambda v: f"{v:.1f}°F", config.INSIDE_CHIP_BLUE, "dew_point"),
        ("dew_point_c", "Dew Point", lambda v: f"{v:.1f}°C", config.INSIDE_CHIP_BLUE, "dew_point"),
        ("pressure_inhg", "Pressure", lambda v: f"{v:.2f} inHg", config.INSIDE_CHIP_AMBER, "pressure"),
        ("pressure_hpa", "Pressure", lambda v: f"{v:.1f} hPa", config.INSIDE_CHIP_AMBER, "pressure"),
        ("pressure_pa", "Pressure", lambda v: f"{v:.0f} Pa", config.INSIDE_CHIP_AMBER, "pressure"),
        ("voc_ohms", "VOC", format_voc_ohms, config.INSIDE_CHIP_PURPLE, "voc"),
        ("voc_index", "VOC Index", lambda v: f"{v:.0f}", config.INSIDE_CHIP_PURPLE, "voc"),
        ("iaq", "IAQ", lambda v: f"{v:.0f}", config.INSIDE_CHIP_PURPLE, "iaq"),
        ("co2_ppm", "CO₂", lambda v: f"{v:.0f} ppm", _mix_color(config.INSIDE_CHIP_BLUE, config.INSIDE_CHIP_AMBER, 0.35), "co2"),
    )

    for key, label, formatter, color, group in known_specs:
        if group and group in used_groups:
            continue
        value = _clean_metric(data.get(key))
        if value is None:
            continue
        metrics.append(dict(label=label, value=formatter(value), color=color))
        used_keys.add(key)
        if group:
            used_groups.add(group)

    skip_keys = {"temp", "temperature"}
    extra_palette_index = 0
    for key in sorted(data.keys()):
        if key in used_keys or key == "temp_f":
            continue
        if any(key.lower().startswith(prefix) for prefix in skip_keys):
            continue
        value = _clean_metric(data.get(key))
        if value is None:
            continue
        color = palette[(len(metrics) + extra_palette_index) % len(palette)]
        extra_palette_index += 1
        metrics.append(
            dict(
                label=_prettify_metric_label(key),
                value=_format_generic_metric_value(key, value),
                color=color,
            )
        )

    return metrics

def draw_inside(display, transition: bool=False):
    provider, read_fn = _probe_sensor()
    if not read_fn:
        logging.warning("draw_inside: sensor not available")
        return None

    try:
        data = read_fn()
        cleaned: Dict[str, Optional[float]] = {}
        if isinstance(data, dict):
            cleaned = {key: _clean_metric(value) for key, value in data.items()}
        else:
            logging.debug("draw_inside: unexpected data payload type %s", type(data))
            cleaned = {}
        temp_f = cleaned.get("temp_f")
    except Exception as e:
        logging.warning(f"draw_inside: sensor read failed: {e}")
        return None

    if temp_f is None:
        logging.warning("draw_inside: temperature missing from sensor data")
        return None

    metrics = _build_metric_entries(cleaned)

    # Title text
    title = "Inside"
    subtitle = provider or ""

    # Compose canvas
    img  = Image.new("RGB", (W, H), config.INSIDE_COL_BG)
    draw = ImageDraw.Draw(img)

    # Fonts (with fallbacks)
    default_title_font = config.FONT_TITLE_SPORTS
    title_base = getattr(config, "FONT_TITLE_INSIDE", None)
    if title_base is None or getattr(title_base, "size", 0) < getattr(default_title_font, "size", 0):
        title_base = default_title_font

    subtitle_base = getattr(config, "FONT_INSIDE_SUBTITLE", None)
    default_subtitle_font = getattr(config, "FONT_DATE_SPORTS", default_title_font)
    if subtitle_base is None or getattr(subtitle_base, "size", 0) < getattr(default_subtitle_font, "size", 0):
        subtitle_base = default_subtitle_font

    temp_base  = getattr(config, "FONT_TIME",        default_title_font)
    label_base = getattr(config, "FONT_INSIDE_LABEL", getattr(config, "FONT_DATE_SPORTS", default_title_font))
    value_base = getattr(config, "FONT_INSIDE_VALUE", getattr(config, "FONT_DATE_SPORTS", default_title_font))

    # --- Title (auto-fit to width without shrinking below the standard size)
    title_side_pad = 8
    title_base_size = getattr(title_base, "size", 30)
    title_sample_h = measure_text(draw, "Hg", title_base)[1]
    title_max_h = max(1, title_sample_h)
    t_font = fit_font(
        draw,
        title,
        title_base,
        max_width=W - 2 * title_side_pad,
        max_height=title_max_h,
        min_pt=min(title_base_size, 12),
        max_pt=title_base_size,
    )
    tw, th = measure_text(draw, title, t_font)
    title_y = 0
    draw.text(((W - tw)//2, title_y), title, font=t_font, fill=config.INSIDE_COL_TITLE)

    subtitle_gap = 6
    if subtitle:
        subtitle_base_size = getattr(subtitle_base, "size", getattr(default_subtitle_font, "size", 24))
        subtitle_sample_h = measure_text(draw, "Hg", subtitle_base)[1]
        subtitle_max_h = max(1, subtitle_sample_h)
        sub_font = fit_font(
            draw,
            subtitle,
            subtitle_base,
            max_width=W - 2 * title_side_pad,
            max_height=subtitle_max_h,
            min_pt=min(subtitle_base_size, 12),
            max_pt=subtitle_base_size,
        )
        sw, sh = measure_text(draw, subtitle, sub_font)
        subtitle_y = title_y + th + subtitle_gap
        draw.text(((W - sw)//2, subtitle_y), subtitle, font=sub_font, fill=config.INSIDE_COL_TITLE)
    else:
        sub_font = t_font
        sw, sh = 0, 0
        subtitle_y = title_y + th

    title_block_h = subtitle_y + (sh if subtitle else 0)

    # Aspect awareness
    is_square = abs(W - H) < 4  # treat as square if nearly equal

    # --- Temperature panel --------------------------------------------------
    if is_square:
        temp_ratio_base = 0.56
        temp_ratio_shrink_per_metric = 0.028
        min_temp_px = max(120, int(H * 0.15))
    else:
        temp_ratio_base = 0.50
        temp_ratio_shrink_per_metric = 0.022
        min_temp_px = max(96, int(H * 0.18))

    temp_value = f"{temp_f:.1f}°F"
    descriptor = ""

    content_top = title_block_h + 12
    bottom_margin = 12
    side_pad = 12
    content_bottom = H - bottom_margin
    content_height = max(1, content_bottom - content_top)

    metric_count = len(metrics)
    _, grid_rows = _metric_grid_dimensions(metric_count, is_square)

    if metric_count:
        temp_ratio = max(0.42, temp_ratio_base - temp_ratio_shrink_per_metric * min(metric_count, 8))
        min_temp = min_temp_px
    else:
        temp_ratio = 0.82 if is_square else 0.72
        min_temp = min_temp_px + (40 if is_square else 24)

    temp_height = min(content_height, max(min_temp, int(content_height * temp_ratio)))

    metric_block_gap = 12 if metric_count else 0
    if metric_count:
        min_metric_row_height = 56 if is_square else 48
        min_metric_gap = 12 if grid_rows > 1 else 0
        target_metrics_height = (
            grid_rows * min_metric_row_height + max(0, grid_rows - 1) * min_metric_gap
        )
        preferred_temp_cap = content_height - (target_metrics_height + metric_block_gap)
        min_temp_floor = min(84 if is_square else 64, content_height)
        preferred_temp_cap = max(min_temp_floor, preferred_temp_cap)
        temp_height = min(temp_height, preferred_temp_cap)
        temp_height = max(min_temp_floor, min(temp_height, content_height))
    else:
        metric_block_gap = 0

    temp_rect = (
        side_pad,
        content_top,
        W - side_pad,
        min(content_bottom, content_top + temp_height),
    )

    _draw_temperature_panel(
        img,
        draw,
        temp_rect,
        temp_f,
        temp_value,
        descriptor,
        getattr(config, "FONT_TIME", getattr(config, "FONT_TITLE_SPORTS", None)),
        getattr(config, "FONT_INSIDE_LABEL", getattr(config, "FONT_DATE_SPORTS", None)),
    )

    if metrics:
        metrics_rect = (
            side_pad,
            min(content_bottom, temp_rect[3] + metric_block_gap),
            W - side_pad,
            content_bottom,
        )
        _draw_metric_rows(draw, metrics_rect, metrics,
                          getattr(config, "FONT_INSIDE_LABEL", getattr(config, "FONT_DATE_SPORTS", None)),
                          getattr(config, "FONT_INSIDE_VALUE", getattr(config, "FONT_DATE_SPORTS", None)),
                          is_square)

    if transition:
        return img

    clear_display(display)
    display.image(img)
    display.show()
    time.sleep(5)
    return None


if __name__ == "__main__":
    try:
        preview = draw_inside(None, transition=True)
        if preview:
            preview.show()
    except Exception:
        pass
