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
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw
from smbus2 import SMBus, i2c_msg

from config import (
    HEIGHT,
    WIDTH,
    FONT_INSIDE_LABEL,
    FONT_INSIDE_VALUE,
    FONT_TEMP,
    FONT_TITLE_INSIDE,
)
from utils import clear_display, log_call

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

# ---- Utils ----
def list_i2c_buses() -> List[int]:
    buses: List[int] = []
    for path in glob.glob("/dev/i2c-*"):
        try:
            buses.append(int(path.split("-")[-1]))
        except Exception:
            pass
    # Ensure stable order: prefer the HyperPixel buses if present
    buses = sorted(set(buses), key=lambda x: (x not in (13,14,15,1), x))
    return buses

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
        Keys: temperature_c, humidity_pct, pressure_hpa, light_lux
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


def _render_metrics(
    draw: ImageDraw.ImageDraw, metrics: List[Tuple[str, str]], *, start_y: int
) -> int:
    y = start_y
    margin = 36
    line_gap = 8
    for label, value in metrics:
        label_w, label_h = draw.textsize(label, font=FONT_INSIDE_LABEL)
        value_w, value_h = draw.textsize(value, font=FONT_INSIDE_VALUE)
        draw.text((margin, y), label, font=FONT_INSIDE_LABEL, fill=(180, 200, 255))
        draw.text((WIDTH - margin - value_w, y), value, font=FONT_INSIDE_VALUE, fill=(255, 255, 255))
        y += max(label_h, value_h) + line_gap
    return y


@log_call
def draw_inside(display, transition=False):
    """Render the primary inside environment screen."""

    readings, timestamp = _fetch_readings()
    clear_display(display)

    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)

    title = "Inside"
    title_w, title_h = draw.textsize(title, font=FONT_TITLE_INSIDE)
    draw.text(((WIDTH - title_w) // 2, 28), title, font=FONT_TITLE_INSIDE, fill=(173, 216, 230))

    temp_value = _format_temperature(readings.get("temperature_c"))
    humidity_value = _format_humidity(readings.get("humidity_pct"))
    pressure_value = _format_pressure(readings.get("pressure_hpa"))
    light_value = _format_light(readings.get("light_lux"))

    temp_text = temp_value or "--"
    temp_w, temp_h = draw.textsize(temp_text, font=FONT_TEMP)
    draw.text(((WIDTH - temp_w) // 2, 80), temp_text, font=FONT_TEMP, fill=(255, 255, 255))

    metrics: List[Tuple[str, str]] = []
    if humidity_value and _has_sensor_source(readings, "humidity_pct"):
        metrics.append(("Humidity", humidity_value))
    if pressure_value and _has_sensor_source(readings, "pressure_hpa"):
        metrics.append(("Pressure", pressure_value))
    if light_value and _has_sensor_source(readings, "light_lux"):
        metrics.append(("Light", light_value))

    if not metrics:
        message = "No sensor data"
        msg_w, msg_h = draw.textsize(message, font=FONT_INSIDE_VALUE)
        draw.text(((WIDTH - msg_w) // 2, HEIGHT - msg_h - 80), message, font=FONT_INSIDE_VALUE, fill=(200, 200, 200))
    else:
        _render_metrics(draw, metrics, start_y=80 + temp_h + 30)

    age_text = _format_age(timestamp)
    if age_text:
        age_w, age_h = draw.textsize(age_text, font=FONT_INSIDE_VALUE)
        draw.text(((WIDTH - age_w) // 2, HEIGHT - age_h - 24), age_text, font=FONT_INSIDE_VALUE, fill=(120, 160, 200))

    return img


@log_call
def draw_inside_sensors(display, transition=False):
    """Render a diagnostic view showing detected sensors and data sources."""

    readings, timestamp = _fetch_readings()
    hub = _ensure_sensor_hub()
    clear_display(display)

    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)

    title = "Inside Sensors"
    title_w, title_h = draw.textsize(title, font=FONT_TITLE_INSIDE)
    draw.text(((WIDTH - title_w) // 2, 28), title, font=FONT_TITLE_INSIDE, fill=(173, 216, 230))

    lines: List[str] = []
    if hub is None:
        lines.append("Sensor hub not initialised")
    else:
        mapping = [
            ("SHT4x", hub.bus_for_sht4x),
            ("BME280", hub.bus_for_bme280),
            ("LTR559", hub.bus_for_ltr559),
            ("LSM6", hub.bus_for_lsm6),
        ]
        for label, info in mapping:
            if info is None:
                lines.append(f"{label}: not detected")
            else:
                bus, addr = info
                lines.append(f"{label}: bus {bus} addr {hex(addr)}")

    sources = readings.get("_sources") if isinstance(readings.get("_sources"), dict) else {}
    if sources:
        lines.append("")
        lines.append("Sources:")
        for metric, source in sorted(sources.items()):
            lines.append(f"  {metric}: {source}")

    metrics: List[Tuple[str, str]] = []
    temp_value = _format_temperature(readings.get("temperature_c"))
    humidity_value = _format_humidity(readings.get("humidity_pct"))
    pressure_value = _format_pressure(readings.get("pressure_hpa"))
    light_value = _format_light(readings.get("light_lux"))
    if temp_value and _has_sensor_source(readings, "temperature_c"):
        metrics.append(("Temperature", temp_value))
    if humidity_value and _has_sensor_source(readings, "humidity_pct"):
        metrics.append(("Humidity", humidity_value))
    if pressure_value and _has_sensor_source(readings, "pressure_hpa"):
        metrics.append(("Pressure", pressure_value))
    if light_value and _has_sensor_source(readings, "light_lux"):
        metrics.append(("Light", light_value))

    y = 80
    if metrics:
        y = _render_metrics(draw, metrics, start_y=y) + 12
    else:
        y += 10

    text_y = y
    for line in lines:
        if not line:
            text_y += FONT_INSIDE_VALUE.size // 2
            continue
        line_w, line_h = draw.textsize(line, font=FONT_INSIDE_VALUE)
        draw.text((36, text_y), line, font=FONT_INSIDE_VALUE, fill=(200, 200, 200))
        text_y += line_h + 6

    age_text = _format_age(timestamp)
    if age_text:
        age_w, age_h = draw.textsize(age_text, font=FONT_INSIDE_VALUE)
        draw.text(((WIDTH - age_w) // 2, HEIGHT - age_h - 24), age_text, font=FONT_INSIDE_VALUE, fill=(120, 160, 200))

    return img
