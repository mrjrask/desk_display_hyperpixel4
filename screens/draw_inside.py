#!/usr/bin/env python3
"""Render helpers for the inside environment screens.

This module combines low-level sensor discovery/reading with Pillow-based
rendering functions that power the ``inside`` and ``inside sensors`` screens.

The ``SensorHub`` class at the top of the file is intentionally lightweight so
it can run on a Raspberry Pi without any additional background service.  The
``draw_inside`` and ``draw_inside_sensors`` functions build user-facing images
from the collected readings.

Supported sensors & default addresses:
    * SHT4x (e.g., SHT41)        : 0x44 (0x45 alt)   -> temperature (°C), humidity (%)
    * BME280                     : 0x76 (0x77 alt)   -> temperature (°C), pressure (hPa), humidity (%)
    * LTR559 (ambient light)     : 0x23              -> light (lux)
    * LSM6DS3/LSM6DSOX (IMU)     : 0x6a (0x6b alt)   -> presence only (no readings here)

Dependencies (install if missing):
    sudo apt-get install -y python3-smbus
    pip3 install smbus2 ltr559 pimoroni-bme280 adafruit-circuitpython-lsm6ds
"""

from __future__ import annotations

import glob
import logging
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

import config

from PIL import Image, ImageDraw
from smbus2 import SMBus, i2c_msg

from config import (
    HEIGHT,
    WIDTH,
    FONT_INSIDE_LABEL,
    FONT_INSIDE_TEMP,
    FONT_INSIDE_VALUE,
    FONT_TITLE_INSIDE,
    INSIDE_SENSOR_I2C_BUS,
)
from utils import (
    clear_display,
    fit_font,
    format_voc_ohms,
    log_call,
    measure_text,
    temperature_color,
)

# Import sensor logger
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from sensor_logger import log_sensor_reading
except Exception:
    log_sensor_reading = None

# Optional imports (we guard usage)
try:
    from bme280 import BME280  # pimoroni-bme280
except Exception:
    BME280 = None

try:
    import ltr559  # pimoroni LTR559
except Exception:
    ltr559 = None

try:
    from adafruit_lsm6ds.lsm6dsox import LSM6DSOX  # optional IMU presence check
except Exception:
    LSM6DSOX = None

# ---- Addresses ----
ADDR_SHT4X = [0x44, 0x45]
ADDR_BME280 = [0x76, 0x77]
ADDR_LTR559 = [0x23]
ADDR_LSM6  = [0x6A, 0x6B]

# HyperPixel hats expose their sensors on predictable I2C buses. We encode the
# priority explicitly so rectangular (13/14) and square (15) panels are tested
# before the generic Raspberry Pi buses.
_HYPERPIXEL_BUS_PRIORITY = (15, 13, 14, 1)


def _preferred_bus_order(buses: List[int]) -> List[int]:
    """Return ``buses`` sorted with HyperPixel priorities and any override."""

    deduped: List[int] = []
    for bus in buses:
        if bus not in deduped:
            deduped.append(bus)

    def _priority_value(bus: int) -> Tuple[int, int]:
        try:
            idx = _HYPERPIXEL_BUS_PRIORITY.index(bus)
        except ValueError:
            idx = len(_HYPERPIXEL_BUS_PRIORITY)
        return (idx, bus)

    ordered = sorted(deduped, key=_priority_value)

    if INSIDE_SENSOR_I2C_BUS is not None:
        override = int(INSIDE_SENSOR_I2C_BUS)
        ordered = [override] + [b for b in ordered if b != override]

    return ordered


def _classify_orientation(ax: float, ay: float, az: float) -> str:
    """Approximate orientation based on accelerometer readings."""

    magnitude = math.sqrt(ax * ax + ay * ay + az * az) or 1e-9
    nx, ny, nz = ax / magnitude, ay / magnitude, az / magnitude

    if abs(nz) > 0.75:
        return "Face up 🙃" if nz > 0 else "Face down 🙃"
    if abs(nx) > abs(ny):
        return "Right edge down" if nx > 0 else "Left edge down"
    return "Top edge down" if ny > 0 else "Bottom edge down"


def _pitch_roll_degrees(ax: float, ay: float, az: float) -> Tuple[float, float]:
    pitch = math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az)))
    roll = math.degrees(math.atan2(ay, math.sqrt(ax * ax + az * az)))
    return pitch, roll


def list_i2c_buses() -> List[int]:
    buses: List[int] = []
    for path in glob.glob("/dev/i2c-*"):
        try:
            buses.append(int(path.split("-")[-1]))
        except Exception:
            pass
    return _preferred_bus_order(buses)

def safe_probe(busnum: int, addr: int, timeout: float = 0.02) -> bool:
    try:
        with SMBus(busnum) as bus:
            # a harmless read of 1 byte from register 0 usually forces an ACK/NACK
            read = i2c_msg.read(addr, 1)
            bus.i2c_rdwr(read)
        return True
    except Exception:
        return False

# ---- SHT4x low-level reader (no external lib required) ----
# Command 0xFD = measure (high precision)
SHT4X_MEASURE_HIGH = 0xFD

def _crc8_sensirion(data: bytes) -> int:
    # Polynomial 0x31, init 0xFF per Sensirion datasheet
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x31
            else:
                crc <<= 1
            crc &= 0xFF
    return crc

def sht4x_read_temp_humidity(busnum: int, addr: int) -> Tuple[float, float]:
    """
    Returns (temperature_C, humidity_percent) from an SHT4x sensor.
    Raises on CRC or I2C errors.
    """
    with SMBus(busnum) as bus:
        bus.write_byte(addr, SHT4X_MEASURE_HIGH)
        time.sleep(0.01)  # 10ms typical; high precision takes ~9.1ms
        data = bus.read_i2c_block_data(addr, 0x00, 6)
    t_raw = bytes(data[0:2])
    t_crc = data[2]
    rh_raw = bytes(data[3:5])
    rh_crc = data[5]
    if _crc8_sensirion(t_raw) != t_crc or _crc8_sensirion(rh_raw) != rh_crc:
        raise RuntimeError("SHT4x CRC check failed")

    t_ticks = (t_raw[0] << 8) | t_raw[1]
    rh_ticks = (rh_raw[0] << 8) | rh_raw[1]
    # From datasheet:
    # T [°C] = -45 + 175 * (t / 65535)
    # RH [%] = 100 * (rh / 65535)
    temperature_c = -45.0 + (175.0 * (t_ticks / 65535.0))
    humidity = 100.0 * (rh_ticks / 65535.0)
    return (temperature_c, humidity)

# ---- Discovery & unified API ----

class SensorHub:
    """
    Discovers sensors at init; exposes get_readings() returning a dict with any available metrics:
       {
         "temperature_c": float,
         "humidity_pct": float,
         "pressure_hpa": float,
         "light_lux": float,
         "sources": { <metric>: "sensor@bus:addr", ... }
       }
    """
    def __init__(self) -> None:
        self.bus_for_sht4x: Optional[Tuple[int, int]] = None   # (busnum, addr)
        self.bus_for_bme280: Optional[Tuple[int, int]] = None  # (busnum, addr)
        self.bus_for_ltr559: Optional[Tuple[int, int]] = None  # (busnum, addr)
        self.bus_for_lsm6: Optional[Tuple[int, int]] = None    # (busnum, addr)

        self._bme280: Optional[BME280] = None
        self._ltr: Optional[object] = None  # ltr559.LTR559 instance
        self._imu: Optional[object] = None  # LSM6DSOX instance

        self._discover_all()

    def _discover_all(self) -> None:
        buses = list_i2c_buses()

        # Probe order favors discrete dedicated sensors for temp/humidity first
        for bus in buses:
            # SHT4x
            for addr in ADDR_SHT4X:
                if safe_probe(bus, addr):
                    try:
                        # quick sanity read to confirm it truly responds
                        _ = sht4x_read_temp_humidity(bus, addr)
                        self.bus_for_sht4x = (bus, addr)
                        break
                    except Exception:
                        # Device may be present but busy; leave for second pass
                        pass
            if self.bus_for_sht4x:
                break

        # BME280
        if BME280 is not None:
            for bus in buses:
                for addr in ADDR_BME280:
                    if safe_probe(bus, addr):
                        try:
                            dev = SMBus(bus)
                            bme = BME280(i2c_dev=dev, i2c_addr=addr)
                            # one read to ensure it initializes
                            _ = bme.get_temperature()
                            self._bme280 = bme
                            self.bus_for_bme280 = (bus, addr)
                            break
                        except Exception:
                            pass
                if self._bme280 is not None:
                    break

        # LTR559
        if ltr559 is not None:
            for bus in buses:
                for addr in ADDR_LTR559:
                    if safe_probe(bus, addr):
                        try:
                            dev = SMBus(bus)
                            sensor = ltr559.LTR559(i2c_dev=dev, i2c_addr=addr)
                            # one read to ensure it initializes
                            _ = sensor.get_lux()
                            self._ltr = sensor
                            self.bus_for_ltr559 = (bus, addr)
                            break
                        except Exception:
                            pass
                if self._ltr is not None:
                    break

        # LSM6DS3/LSM6DSOX (presence only; no readings used here)
        if LSM6DSOX is not None:
            for bus in buses:
                for addr in ADDR_LSM6:
                    if safe_probe(bus, addr):
                        try:
                            dev = SMBus(bus)
                            imu = LSM6DSOX(i2c_dev=dev, i2c_addr=addr)
                            self._imu = imu
                            self.bus_for_lsm6 = (bus, addr)
                            break
                        except Exception:
                            pass
                if self._imu is not None:
                    break

    def get_readings(self) -> Dict[str, float]:
        """
        Returns a dictionary with any available metrics.
        Keys: temperature_c, humidity_pct, pressure_hpa, light_lux,
        proximity, accel_ms2 (tuple), gyro_rads (tuple), pitch_deg, roll_deg,
        orientation_label
        Plus a "sources" dict indicating which sensor supplied each metric.
        """
        out: Dict[str, float] = {}
        sources: Dict[str, str] = {}

        # Priority: SHT4x for temp/humidity (high accuracy), else BME280
        # Temperature / Humidity
        if self.bus_for_sht4x is not None:
            bus, addr = self.bus_for_sht4x
            try:
                t, h = sht4x_read_temp_humidity(bus, addr)
                out["temperature_c"] = t
                out["humidity_pct"] = h
                sources["temperature_c"] = f"SHT4x@{bus}:{hex(addr)}"
                sources["humidity_pct"] = f"SHT4x@{bus}:{hex(addr)}"
            except Exception:
                # fall through to BME280 if available
                pass

        if ("temperature_c" not in out or "humidity_pct" not in out) and self._bme280 is not None:
            try:
                t = float(self._bme280.get_temperature())
                h = float(self._bme280.get_humidity())  # %RH
                out.setdefault("temperature_c", t)
                out.setdefault("humidity_pct", h)
                if "temperature_c" not in sources:
                    sources["temperature_c"] = self._fmt_bme()
                if "humidity_pct" not in sources:
                    sources["humidity_pct"] = self._fmt_bme()
            except Exception:
                pass

        # Pressure (BME280)
        if self._bme280 is not None:
            try:
                p = float(self._bme280.get_pressure())  # hPa
                out["pressure_hpa"] = p
                sources["pressure_hpa"] = self._fmt_bme()
            except Exception:
                pass

        # Light (LTR559)
        if self._ltr is not None:
            try:
                lux = float(self._ltr.get_lux())
                out["light_lux"] = lux
                b, a = self.bus_for_ltr559
                sources["light_lux"] = f"LTR559@{b}:{hex(a)}"
            except Exception:
                pass

            try:
                proximity = int(self._ltr.get_proximity())
                out["proximity"] = proximity
                b, a = self.bus_for_ltr559
                sources.setdefault("proximity", f"LTR559@{b}:{hex(a)}")
            except Exception:
                pass

        # IMU (LSM6DSOX) - orientation + raw accel/gyro
        if self._imu is not None:
            try:
                accel = getattr(self._imu, "acceleration", None)
                if accel:
                    ax, ay, az = accel
                    out["accel_ms2"] = accel
                    pitch, roll = _pitch_roll_degrees(ax, ay, az)
                    out["pitch_deg"] = pitch
                    out["roll_deg"] = roll
                    out["orientation_label"] = _classify_orientation(ax, ay, az)
                    b, a = self.bus_for_lsm6
                    label = f"LSM6@{b}:{hex(a)}"
                    sources.setdefault("accel_ms2", label)
                    sources.setdefault("orientation_label", label)
                    sources.setdefault("pitch_deg", label)
                    sources.setdefault("roll_deg", label)
            except Exception:
                pass

            try:
                gyro = getattr(self._imu, "gyro", None)
                if gyro is None:
                    gyro = getattr(self._imu, "gyroscope", None)
                if gyro:
                    out["gyro_rads"] = gyro
                    b, a = self.bus_for_lsm6
                    sources.setdefault("gyro_rads", f"LSM6@{b}:{hex(a)}")
            except Exception:
                pass

        # Attach sources
        out["sources_info_count"] = len(sources)
        # Not user-visible in UI unless you print it there; useful for logging
        out["_sources"] = sources
        return out

    def _fmt_bme(self) -> str:
        if self.bus_for_bme280 is None:
            return "BME280@unknown"
        b, a = self.bus_for_bme280
        return f"BME280@{b}:{hex(a)}"


# ---- Rendering helpers -------------------------------------------------------

_SENSOR_HUB: Optional[SensorHub] = None
_HUB_LOCK = threading.Lock()
_HUB_LAST_FAILURE: Optional[float] = None
_HUB_RETRY_INTERVAL = 60.0  # seconds

_CACHE_TTL = 30.0  # seconds
_CACHE_MAX_STALE = 300.0
_cached_readings: Optional[Tuple[float, Dict[str, Any]]] = None


def _ensure_sensor_hub() -> Optional[SensorHub]:
    """Lazily construct the shared ``SensorHub`` instance."""

    global _SENSOR_HUB, _HUB_LAST_FAILURE
    with _HUB_LOCK:
        if _SENSOR_HUB is not None:
            return _SENSOR_HUB

        now = time.monotonic()
        if _HUB_LAST_FAILURE is not None and now - _HUB_LAST_FAILURE < _HUB_RETRY_INTERVAL:
            return None

        try:
            _SENSOR_HUB = SensorHub()
            logging.info("Initialised SensorHub for inside screen")
            return _SENSOR_HUB
        except Exception:
            _HUB_LAST_FAILURE = now
            logging.exception("Failed to initialise SensorHub; will retry later")
            return None


def _fetch_readings(force_refresh: bool = False) -> Tuple[Dict[str, Any], Optional[float]]:
    """Return cached sensor readings and the timestamp they were captured."""

    global _cached_readings
    now = time.monotonic()

    if (
        not force_refresh
        and _cached_readings is not None
        and now - _cached_readings[0] <= _CACHE_TTL
    ):
        return _cached_readings[1], _cached_readings[0]

    hub = _ensure_sensor_hub()
    if hub is None:
        # Fallback to slightly stale data if available.
        if _cached_readings is not None and now - _cached_readings[0] <= _CACHE_MAX_STALE:
            return _cached_readings[1], _cached_readings[0]
        return {}, None

    try:
        readings = hub.get_readings()
    except Exception:
        logging.exception("Failed to read from SensorHub")
        if _cached_readings is not None and now - _cached_readings[0] <= _CACHE_MAX_STALE:
            return _cached_readings[1], _cached_readings[0]
        return {}, None

    _cached_readings = (now, readings)
    return readings, now


def _c_to_f(value: float) -> float:
    return (value * 9.0 / 5.0) + 32.0


def _format_temperature(temp_c: Optional[float]) -> Optional[str]:
    if temp_c is None:
        return None
    try:
        temp_f = _c_to_f(float(temp_c))
        return f"{temp_f:.1f}°F"
    except (TypeError, ValueError):
        return None


def _format_humidity(humidity: Optional[float]) -> Optional[str]:
    if humidity is None:
        return None
    try:
        return f"{max(0.0, min(100.0, float(humidity))):.0f}%"
    except (TypeError, ValueError):
        return None


def _format_pressure(pressure_hpa: Optional[float]) -> Optional[str]:
    if pressure_hpa is None:
        return None
    try:
        in_hg = float(pressure_hpa) * 0.0295299830714
        return f"{in_hg:.2f} inHg"
    except (TypeError, ValueError):
        return None


def _format_light(light_lux: Optional[float]) -> Optional[str]:
    if light_lux is None:
        return None
    try:
        lux = float(light_lux)
    except (TypeError, ValueError):
        return None
    if lux >= 1000:
        return f"{lux/1000:.1f} klx"
    return f"{lux:.0f} lx"


def _format_proximity(proximity: Optional[float]) -> Optional[str]:
    if proximity is None:
        return None
    try:
        return f"{int(proximity)}"
    except (TypeError, ValueError):
        return None


def _format_temp_dual(temp_c: Optional[float]) -> Optional[str]:
    if temp_c is None:
        return None
    try:
        temp_c_val = float(temp_c)
        temp_f = _c_to_f(temp_c_val)
        return f"{temp_c_val:.1f}°C / {temp_f:.1f}°F"
    except (TypeError, ValueError):
        return None


def _format_pitch_roll(pitch: Optional[float], roll: Optional[float]) -> Optional[str]:
    try:
        if pitch is None or roll is None:
            return None
        return f"{float(pitch):5.1f}° / {float(roll):5.1f}°"
    except (TypeError, ValueError):
        return None


def _format_vector(values: Any, unit: str) -> Optional[str]:
    try:
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            return None
        if all(isinstance(v, int) for v in values):
            ax, ay, az = [int(v) for v in values]
            return f"ax={ax:7d} ay={ay:7d} az={az:7d}"

        ax, ay, az = [float(v) for v in values]
    except (TypeError, ValueError):
        return None

    return f"ax={ax:6.2f} ay={ay:6.2f} az={az:6.2f} {unit}"


def _compute_dewpoint(temp_c: Optional[float], humidity: Optional[float]) -> Optional[str]:
    if temp_c is None or humidity is None:
        return None
    try:
        t = float(temp_c)
        rh = max(0.1, min(100.0, float(humidity)))
    except (TypeError, ValueError):
        return None

    a = 17.62
    b = 243.12
    gamma = (a * t / (b + t)) + math.log(rh / 100.0)
    dew_c = (b * gamma) / (a - gamma)
    dew_f = _c_to_f(dew_c)
    return f"{dew_f:.1f}°F"


def _has_sensor_source(readings: Dict[str, Any], metric_key: str) -> bool:
    sources = readings.get("_sources")
    if not isinstance(sources, dict):
        return False
    return metric_key in sources


def _format_age(timestamp: Optional[float]) -> Optional[str]:
    if timestamp is None:
        return None
    age = max(0.0, time.monotonic() - timestamp)
    if age < 1.0:
        return "just now"
    if age < 60.0:
        return f"{age:.0f}s ago"
    minutes = age // 60.0
    if minutes < 60:
        return f"{minutes:.0f}m ago"
    hours = minutes // 60.0
    return f"{hours:.0f}h ago"


def _dew_point_f(temp_c: Optional[float], humidity_pct: Optional[float]) -> Optional[float]:
    if temp_c is None or humidity_pct is None:
        return None
    try:
        t = float(temp_c)
        rh = float(humidity_pct)
    except Exception:
        return None
    if rh <= 0:
        return None
    a = 17.62
    b = 243.12
    gamma = (a * t / (b + t)) + math.log(rh / 100.0)
    dew_c = (b * gamma) / (a - gamma)
    return _c_to_f(dew_c)


def _mix_color(color: Tuple[int, int, int], target: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    factor = max(0.0, min(1.0, factor))
    return tuple(int(round(color[idx] * (1 - factor) + target[idx] * factor)) for idx in range(3))


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
        temp_font = clone_font(temp_font, next_size)
        temp_bbox = draw.textbbox((0, 0), temp_text, font=temp_font)
        temp_w = temp_bbox[2] - temp_bbox[0]
        temp_h = temp_bbox[3] - temp_bbox[1]

    temp_x = x0 + padding_x
    temp_y = max(label_y + label_h + value_gap, y0 + (height - temp_h) // 2)

    draw.text((label_x, label_y), label_text, font=label_font, fill=_mix_color(color, config.INSIDE_COL_TEXT, 0.35))
    draw.text((temp_x, temp_y), temp_text, font=temp_font, fill=config.INSIDE_COL_TEXT)
    if has_descriptor and desc_font is not None:
        draw.text((desc_x, desc_y), descriptor, font=desc_font, fill=_mix_color(color, config.INSIDE_COL_TEXT, 0.35))


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
    radius = max(6, min(18, min(width, height) // 6))
    bg = _mix_color(accent, config.INSIDE_COL_BG, 0.3)
    outline = _mix_color(accent, config.INSIDE_COL_BG, 0.18)
    draw.rounded_rectangle(rect, radius=radius, fill=bg, outline=outline, width=1)

    padding_x = max(10, width // 14)
    padding_y = max(8, height // 12)

    max_label_height = max(14, int(height * 0.36))
    max_value_height = max(16, int(height * 0.48))

    label_base_size = getattr(label_base, "size", 18)
    value_base_size = getattr(value_base, "size", 20)

    label_font = fit_font(
        draw,
        label,
        label_base,
        max_width=width - 2 * padding_x,
        max_height=max_label_height,
        min_pt=min(label_base_size, 10),
        max_pt=label_base_size,
    )
    label_w, label_h = measure_text(draw, label, label_font)

    min_gap = max(4, height // 16)
    available_width = max(1, width - 2 * padding_x)
    value_font = value_base
    value_w, value_h = measure_text(draw, value, value_font)
    if value_h > max_value_height or value_w > available_width:
        value_font = fit_font(
            draw,
            value,
            value_base,
            max_width=available_width,
            max_height=max_value_height,
            min_pt=min(value_base_size, 10),
            max_pt=value_base_size,
        )
        value_w, value_h = measure_text(draw, value, value_font)
    if value_h + label_h + min_gap > height:
        value_font = fit_font(
            draw,
            value,
            value_font,
            max_width=available_width,
            max_height=max(12, height - label_h - min_gap),
            min_pt=10,
            max_pt=getattr(value_font, "size", value_base_size),
        )
        value_w, value_h = measure_text(draw, value, value_font)

    label_w = min(label_w, available_width)
    value_w = min(value_w, available_width)

    label_x = x0 + padding_x
    label_y = y0 + padding_y
    value_x = x0 + padding_x
    value_y = y1 - padding_y - value_h
    min_gap = max(6, height // 12)
    if value_y - (label_y + label_h) < min_gap:
        value_y = min(y1 - padding_y - value_h, label_y + label_h + min_gap)

    label_color = _mix_color(accent, config.INSIDE_COL_TEXT, 0.25)
    value_color = config.INSIDE_COL_TEXT

    draw.text((label_x, label_y), label, font=label_font, fill=label_color)
    draw.text((value_x, value_y), value, font=value_font, fill=value_color)


def _metric_grid_dimensions(count: int) -> Tuple[int, int]:
    if count <= 0:
        return 0, 0
    if count <= 2:
        columns = count
    elif count <= 6:
        columns = 2
    else:
        columns = 3
    columns = max(1, columns)
    rows = int(math.ceil(count / columns))
    return columns, rows


def _draw_metric_rows(
    draw: ImageDraw.ImageDraw,
    rect: Tuple[int, int, int, int],
    metrics: Sequence[Dict[str, Any]],
    label_base,
    value_base,
) -> None:
    x0, y0, x1, y1 = rect
    count = len(metrics)
    width = max(0, x1 - x0)
    height = max(0, y1 - y0)
    if count <= 0 or width <= 0 or height <= 0:
        return

    columns, rows = _metric_grid_dimensions(count)
    if columns <= 0 or rows <= 0:
        return

    if columns > 1:
        desired_h_gap = max(8, width // 30)
        max_h_gap = max(0, (width - columns) // (columns - 1))
        h_gap = min(desired_h_gap, max_h_gap)
    else:
        h_gap = 0
    if rows > 1:
        desired_v_gap = max(8, height // 30)
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


def _primary_source_label(readings: Dict[str, Any]) -> Optional[str]:
    sources = readings.get("_sources")
    if not isinstance(sources, dict):
        return None
    for key in (
        "temperature_c",
        "humidity_pct",
        "pressure_hpa",
        "light_lux",
    ):
        source = sources.get(key)
        if isinstance(source, str):
            return source
    return None


def _format_sensor_age(timestamp: Optional[float]) -> Optional[str]:
    age = _format_age(timestamp)
    if not age:
        return None
    return f"Updated {age}"


@log_call
def draw_inside(display, transition: bool = False):
    """Render a calmer, card-based inside environment screen."""

    readings, timestamp = _fetch_readings()

    if log_sensor_reading is not None and readings:
        try:
            log_sensor_reading(readings)
        except Exception:
            pass

    img = Image.new("RGB", (WIDTH, HEIGHT), config.INSIDE_COL_BG)
    draw = ImageDraw.Draw(img)

    temp_c = readings.get("temperature_c")
    temp_f = _c_to_f(temp_c) if temp_c is not None else None
    temp_value = f"{temp_f:.1f}°F" if temp_f is not None else "--°F"

    metrics_payload: Dict[str, Optional[float]] = {}
    humidity = readings.get("humidity_pct")
    pressure_hpa = readings.get("pressure_hpa")
    light = readings.get("light_lux")

    if humidity is not None:
        metrics_payload["humidity"] = humidity
    dew_point = _dew_point_f(temp_c, humidity)
    if dew_point is not None:
        metrics_payload["dew_point_f"] = dew_point
    if pressure_hpa is not None:
        metrics_payload["pressure_inhg"] = pressure_hpa * 0.02953
    if light is not None:
        metrics_payload["light_lux"] = light

    metrics = _build_metric_entries(metrics_payload)

    title = "Inside"
    subtitle = _primary_source_label(readings) or _format_sensor_age(timestamp) or ""

    title_base = FONT_TITLE_INSIDE
    subtitle_base = FONT_INSIDE_LABEL
    temp_base = FONT_INSIDE_TEMP
    label_base = FONT_INSIDE_LABEL
    value_base = FONT_INSIDE_VALUE

    title_side_pad = 8
    title_base_size = getattr(title_base, "size", 30)
    title_sample_h = measure_text(draw, "Hg", title_base)[1]
    title_max_h = max(1, title_sample_h)
    t_font = fit_font(
        draw,
        title,
        title_base,
        max_width=WIDTH - 2 * title_side_pad,
        max_height=title_max_h,
        min_pt=min(title_base_size, 12),
        max_pt=title_base_size,
    )
    tw, th = measure_text(draw, title, t_font)
    title_y = 4
    draw.text(((WIDTH - tw) // 2, title_y), title, font=t_font, fill=config.INSIDE_COL_TITLE)

    subtitle_gap = 6
    if subtitle:
        subtitle_base_size = getattr(subtitle_base, "size", getattr(title_base, "size", 18))
        subtitle_sample_h = measure_text(draw, "Hg", subtitle_base)[1]
        subtitle_max_h = max(1, subtitle_sample_h)
        sub_font = fit_font(
            draw,
            subtitle,
            subtitle_base,
            max_width=WIDTH - 2 * title_side_pad,
            max_height=subtitle_max_h,
            min_pt=min(subtitle_base_size, 12),
            max_pt=subtitle_base_size,
        )
        sw, sh = measure_text(draw, subtitle, sub_font)
        subtitle_y = title_y + th + subtitle_gap
        draw.text(((WIDTH - sw) // 2, subtitle_y), subtitle, font=sub_font, fill=_mix_color(config.INSIDE_COL_TITLE, config.INSIDE_COL_BG, 0.15))
    else:
        sh = 0
        subtitle_y = title_y + th

    title_block_h = subtitle_y + (sh if subtitle else 0)

    content_top = title_block_h + 12
    bottom_margin = 12
    side_pad = 12
    content_bottom = HEIGHT - bottom_margin
    content_height = max(1, content_bottom - content_top)

    metric_count = len(metrics)
    _, grid_rows = _metric_grid_dimensions(metric_count)
    if metric_count:
        temp_ratio = max(0.42, 0.58 - 0.03 * min(metric_count, 6))
        min_temp = max(84, 118 - 8 * min(metric_count, 6))
    else:
        temp_ratio = 0.82
        min_temp = 128

    temp_height = min(content_height, max(min_temp, int(content_height * temp_ratio)))
    metric_block_gap = 12 if metric_count else 0
    if metric_count:
        min_metric_row_height = 44
        min_metric_gap = 10 if grid_rows > 1 else 0
        target_metrics_height = (
            grid_rows * min_metric_row_height + max(0, grid_rows - 1) * min_metric_gap
        )
        preferred_temp_cap = content_height - (target_metrics_height + metric_block_gap)
        min_temp_floor = min(54, content_height)
        preferred_temp_cap = max(min_temp_floor, preferred_temp_cap)
        temp_height = min(temp_height, preferred_temp_cap)
        temp_height = max(min_temp_floor, min(temp_height, content_height))
    else:
        metric_block_gap = 0
    temp_rect = (
        side_pad,
        content_top,
        WIDTH - side_pad,
        min(content_bottom, content_top + temp_height),
    )

    _draw_temperature_panel(
        img,
        draw,
        temp_rect,
        temp_f if temp_f is not None else 72.0,
        temp_value,
        "",
        temp_base,
        label_base,
    )

    if metrics:
        metrics_rect = (
            side_pad,
            min(content_bottom, temp_rect[3] + metric_block_gap),
            WIDTH - side_pad,
            content_bottom,
        )
        _draw_metric_rows(draw, metrics_rect, metrics, label_base, value_base)
    elif temp_f is None:
        message = "No sensor data"
        msg_w, msg_h = measure_text(draw, message, value_base)
        msg_y = temp_rect[3] + 8
        draw.text(((WIDTH - msg_w) // 2, msg_y), message, font=value_base, fill=_mix_color(config.INSIDE_COL_TEXT, config.INSIDE_COL_BG, 0.4))

    if transition:
        return img

    clear_display(display)
    display.image(img)
    display.show()
    time.sleep(5)
    return None


@log_call
def draw_inside_sensors(display, transition: bool = False):
    """Diagnostic view that mirrors the refreshed inside layout."""

    readings, timestamp = _fetch_readings(force_refresh=True)
    hub = _ensure_sensor_hub()

    img = Image.new("RGB", (WIDTH, HEIGHT), config.INSIDE_COL_BG)
    draw = ImageDraw.Draw(img)

    title = "Inside Sensors"
    subtitle = _primary_source_label(readings) or _format_sensor_age(timestamp) or ""

    title_font = FONT_TITLE_INSIDE
    subtitle_font = FONT_INSIDE_LABEL
    title_w, title_h = measure_text(draw, title, title_font)
    draw.text(((WIDTH - title_w) // 2, 4), title, font=title_font, fill=config.INSIDE_COL_TITLE)
    title_block_h = title_h
    if subtitle:
        sub_font = fit_font(
            draw,
            subtitle,
            subtitle_font,
            max_width=WIDTH - 16,
            max_height=subtitle_font.size if hasattr(subtitle_font, "size") else 18,
            min_pt=10,
            max_pt=getattr(subtitle_font, "size", 18),
        )
        sw, sh = measure_text(draw, subtitle, sub_font)
        draw.text(((WIDTH - sw) // 2, title_h + 8), subtitle, font=sub_font, fill=_mix_color(config.INSIDE_COL_TITLE, config.INSIDE_COL_BG, 0.15))
        title_block_h = title_h + 8 + sh

    metrics_payload: Dict[str, Optional[float]] = {}
    metrics_payload["humidity"] = readings.get("humidity_pct")
    metrics_payload["pressure_hpa"] = readings.get("pressure_hpa")
    metrics_payload["light_lux"] = readings.get("light_lux")
    metrics_payload["temp_f"] = _c_to_f(readings.get("temperature_c")) if readings.get("temperature_c") is not None else None
    dew_point = _dew_point_f(readings.get("temperature_c"), readings.get("humidity_pct"))
    if dew_point is not None:
        metrics_payload["dew_point_f"] = dew_point
    metrics = _build_metric_entries(metrics_payload)

    content_top = title_block_h + 12
    content_bottom = HEIGHT - 54
    side_pad = 12

    if metrics:
        metrics_rect = (side_pad, content_top, WIDTH - side_pad, content_bottom)
        _draw_metric_rows(draw, metrics_rect, metrics, FONT_INSIDE_LABEL, FONT_INSIDE_VALUE)
        content_top = metrics_rect[3] + 8

    sensor_lines: List[str] = []
    if hub is None:
        sensor_lines.append("Sensor hub not initialised")
    else:
        mapping = [
            ("SHT4x", hub.bus_for_sht4x),
            ("BME280", hub.bus_for_bme280),
            ("LTR559", hub.bus_for_ltr559),
            ("LSM6", hub.bus_for_lsm6),
        ]
        for label, info in mapping:
            if info is None:
                sensor_lines.append(f"{label}: not detected")
            else:
                bus, addr = info
                sensor_lines.append(f"{label}: bus {bus} addr {hex(addr)}")

    sources = readings.get("_sources") if isinstance(readings.get("_sources"), dict) else {}
    if sources:
        sensor_lines.append("Sources:")
        for metric, source in sorted(sources.items()):
            sensor_lines.append(f"  {metric}: {source}")

    y = max(content_top, HEIGHT - 54)
    line_font = FONT_INSIDE_VALUE
    for line in sensor_lines:
        if not line:
            y += line_font.size // 2
            continue
        lw, lh = measure_text(draw, line, line_font)
        draw.text((side_pad, y), line, font=line_font, fill=_mix_color(config.INSIDE_COL_TEXT, config.INSIDE_COL_BG, 0.2))
        y += lh + 4

    age_text = _format_sensor_age(timestamp)
    if age_text:
        age_w, age_h = measure_text(draw, age_text, FONT_INSIDE_VALUE)
        draw.text(((WIDTH - age_w) // 2, HEIGHT - age_h - 8), age_text, font=FONT_INSIDE_VALUE, fill=_mix_color(config.INSIDE_COL_TEXT, config.INSIDE_COL_BG, 0.35))

    if transition:
        return img

    clear_display(display)
    display.image(img)
    display.show()
    time.sleep(5)
    return None
