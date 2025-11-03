#!/usr/bin/env python3
# inside_sensor.py (HyperPixel friendly)
# Read indoor sensors over a specified Linux I2C bus using adafruit_extended_bus.
# Supports: SHT41 (SHT4x), BME280, BME680, BME688 (via bme68x), LTR559 (lux/prox), LSM6DS3 (IMU)
# Picks up INSIDE_SENSOR_I2C_BUS if set; otherwise tries likely buses automatically.

import logging
import os
from typing import Optional, Dict, Any, List, Tuple

from adafruit_extended_bus import ExtendedI2C as I2C

# --- Optional sensor libs (import if installed) -------------------------------
try:
    import adafruit_bme280.advanced as adafruit_bme280
except Exception:
    adafruit_bme280 = None

try:
    import adafruit_bme680
except Exception:
    adafruit_bme680 = None

try:
    import adafruit_sht4x
except Exception:
    adafruit_sht4x = None

try:
    import adafruit_lsm6ds
    from adafruit_lsm6ds.lsm6ds3 import LSM6DS3
except Exception:
    adafruit_lsm6ds = None
    LSM6DS3 = None

try:
    import ltr559  # Pimoroni ambient/proximity
except Exception:
    ltr559 = None

# Bosch / Pimoroni low-level BME68x family (BME680/688). Provides raw-ish access.
try:
    import bme68x  # type: ignore
except Exception:
    bme68x = None

# --- Addresses to consider ----------------------------------------------------
ADDR = {
    "BME280": [0x76, 0x77],
    "BME680": [0x76, 0x77],   # same pair
    "SHT4X":  [0x44, 0x45],
    "LSM6DS": [0x6A, 0x6B],
    "LTR559": [0x23],         # typical for LTR559
    # BME68x lib will probe device id; we still scan the common addresses
    "BME68X": [0x76, 0x77],
}

LIKELY_BUSES_DEFAULT = [15, 13, 14, 1, 0, 10]

def _dedupe(seq):
    seen = set()
    out = []
    for x in seq:
        if x is None or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out

def _scan(bus: int) -> List[int]:
    found = []
    try:
        i2c = I2C(bus)
        for addr in range(0x03, 0x78):
            try:
                i2c.writeto(addr, b"")
                found.append(addr)
            except OSError:
                pass
        try:
            i2c.deinit()
        except Exception:
            pass
    except Exception:
        pass
    return found

def _any_known(addrs: List[int]) -> bool:
    for group in ADDR.values():
        for a in group:
            if a in addrs:
                return True
    return False

# --- Per-sensor init + read helpers ------------------------------------------
def _init_bme280(bus: int):
    if not adafruit_bme280:
        return None
    for a in ADDR["BME280"]:
        try:
            i2c = I2C(bus)
            dev = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=a)
            # sanity read
            _ = dev.temperature
            return dev
        except Exception:
            try:
                i2c.deinit()
            except Exception:
                pass
    return None

def _read_bme280(dev) -> Dict[str, Any]:
    return {
        "temperature_c": float(dev.temperature),
        "humidity_percent": float(dev.humidity),
        "pressure_hpa": float(dev.pressure),
        "gas_ohms": None,
        "sensor_model": "BME280",
    }

def _init_bme680(bus: int):
    if not adafruit_bme680:
        return None
    for a in ADDR["BME680"]:
        try:
            i2c = I2C(bus)
            dev = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=a)
            _ = dev.temperature
            return dev
        except Exception:
            try:
                i2c.deinit()
            except Exception:
                pass
    return None

def _read_bme680(dev) -> Dict[str, Any]:
    # gas is in ohms; humidity and pressure available
    return {
        "temperature_c": float(dev.temperature),
        "humidity_percent": float(dev.humidity),
        "pressure_hpa": float(dev.pressure),
        "gas_ohms": float(getattr(dev, "gas", 0.0)),
        "sensor_model": "BME680",
    }

def _init_bme68x(bus: int):
    # BME68x supports BME680/688; works directly via bus number
    if not bme68x:
        return None
    for a in ADDR["BME68X"]:
        try:
            # The lib exposes a convenience class using bus/address
            dev = bme68x.BME68X(i2c_bus=bus, i2c_address=a)  # type: ignore
            # configure oversampling minimally
            dev.set_humidity_oversampling(bme68x.OS_2X)   # type: ignore
            dev.set_pressure_oversampling(bme68x.OS_4X)   # type: ignore
            dev.set_temperature_oversampling(bme68x.OS_8X)# type: ignore
            # try a read
            data = dev.get_data()                          # type: ignore
            if data:
                return dev
        except Exception:
            pass
    return None

def _read_bme68x(dev) -> Dict[str, Any]:
    try:
        data = dev.get_data()  # returns list/tuple of samples
        if isinstance(data, (list, tuple)) and data:
            s = data[0]
            # The exact attribute names vary by lib version; try common ones:
            t = float(getattr(s, "temperature", getattr(s, "temp", 0.0)))
            h = float(getattr(s, "humidity", getattr(s, "rh", 0.0)))
            p = float(getattr(s, "pressure", getattr(s, "press", 0.0)))
            g = float(getattr(s, "gas_resistance", getattr(s, "gas_res", 0.0)))
            return {
                "temperature_c": t,
                "humidity_percent": h,
                "pressure_hpa": p,
                "gas_ohms": g,
                "sensor_model": "BME68x",
            }
    except Exception as e:
        return {"error": f"BME68x read failed: {e}"}
    return {"error": "BME68x returned no samples"}

def _init_sht4x(bus: int):
    if not adafruit_sht4x:
        return None
    for a in ADDR["SHT4X"]:
        try:
            i2c = I2C(bus)
            dev = adafruit_sht4x.SHT4x(i2c, address=a)
            # sanity read
            _t, _h = dev.measurements
            return dev
        except Exception:
            try:
                i2c.deinit()
            except Exception:
                pass
    return None

def _read_sht4x(dev) -> Dict[str, Any]:
    t, h = dev.measurements
    return {
        "temperature_c": float(t),
        "humidity_percent": float(h),
        "pressure_hpa": None,
        "gas_ohms": None,
        "sensor_model": "SHT4x",
    }

def _init_ltr559(bus: int):
    if not ltr559:
        return None
    # Pimoroni lib auto-detects on default address 0x23; we just instantiate.
    try:
        # The driver uses smbus through /dev/i2c-X; it figures out bus from env or default 1.
        # We can set environment so it uses our bus:
        os.environ["PIMORONI_I2C_BUS"] = str(bus)
        dev = ltr559.LTR559()
        # quick read
        _ = dev.get_lux()
        return dev
    except Exception:
        return None

def _read_ltr559(dev) -> Dict[str, Any]:
    try:
        lux = float(dev.get_lux())
        prox = int(dev.get_proximity())
    except Exception as e:
        return {"error": f"LTR559 read failed: {e}"}
    return {
        "als_lux": lux,
        "proximity": prox,
        "sensor_model": "LTR559",
    }

def _init_lsm6ds(bus: int):
    if not (adafruit_lsm6ds and LSM6DS3):
        return None
    for a in ADDR["LSM6DS"]:
        try:
            i2c = I2C(bus)
            dev = LSM6DS3(i2c, address=a)
            _ = dev.acceleration
            return dev
        except Exception:
            try:
                i2c.deinit()
            except Exception:
                pass
    return None

def _read_lsm6ds(dev) -> Dict[str, Any]:
    ax, ay, az = dev.acceleration
    gx, gy, gz = dev.gyro
    return {
        "accel_m_s2": (float(ax), float(ay), float(az)),
        "gyro_rad_s": (float(gx), float(gy), float(gz)),
        "sensor_model": "LSM6DS3",
    }

# --- Main probe/read API ------------------------------------------------------
def _candidate_buses() -> List[int]:
    override_raw = os.getenv("INSIDE_SENSOR_I2C_BUS")
    override: Optional[int] = None
    if override_raw is not None:
        try:
            override = int(override_raw)
        except (TypeError, ValueError):
            logging.warning(
                "Invalid INSIDE_SENSOR_I2C_BUS value %r; ignoring override", override_raw
            )

    buses: List[Optional[int]] = []
    if override is not None:
        buses.append(override)
    buses.extend(LIKELY_BUSES_DEFAULT)
    return _dedupe(buses)

def read_all() -> Dict[str, Any]:
    """
    Scan likely buses, pick the first that yields any supported sensor,
    and return a dict with readings and a scan map.
    """
    scan_map: Dict[int, List[int]] = {}
    # 1) quick scans to map buses
    for bus in _candidate_buses():
        scan_map[bus] = _scan(bus)

    # 2) choose a bus with any known address if possible, else fall back to first candidate
    buses_sorted = sorted(_candidate_buses(), key=lambda b: int(b != _candidate_buses()[0]))
    chosen = None
    for bus in buses_sorted:
        if _any_known(scan_map[bus]):
            chosen = bus
            break
    if chosen is None:
        chosen = _candidate_buses()[0]

    # 3) try to init sensors on chosen bus
    results: Dict[str, Any] = {"bus": chosen, "scan_map": scan_map, "sensors": {}}

    # Priority: environmental first (used by 'inside' screen)
    bme68x_dev = _init_bme68x(chosen)
    if bme68x_dev:
        results["sensors"]["env_primary"] = _read_bme68x(bme68x_dev)
    else:
        bme680_dev = _init_bme680(chosen)
        if bme680_dev:
            results["sensors"]["env_primary"] = _read_bme680(bme680_dev)
        else:
            bme280_dev = _init_bme280(chosen)
            if bme280_dev:
                results["sensors"]["env_primary"] = _read_bme280(bme280_dev)

    # Secondary humidity-only candidate
    sht4x_dev = _init_sht4x(chosen)
    if sht4x_dev:
        results["sensors"]["sht4x"] = _read_sht4x(sht4x_dev)

    # Light/proximity (Multi-Sensor Stick)
    ltr = _init_ltr559(chosen)
    if ltr:
        results["sensors"]["ltr559"] = _read_ltr559(ltr)

    # IMU (Multi-Sensor Stick)
    lsm = _init_lsm6ds(chosen)
    if lsm:
        results["sensors"]["lsm6ds"] = _read_lsm6ds(lsm)

    # Final check
    if not results["sensors"]:
        results["error"] = (
            "No supported sensors initialized on available buses. "
            "Confirm packages are installed and I2C bus is correct."
        )
    return results

if __name__ == "__main__":
    out = read_all()
    for k, v in out.items():
        print(f"{k}: {v}")
    if out.get("error"):
        raise SystemExit(1)
