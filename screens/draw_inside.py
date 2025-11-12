#!/usr/bin/env python3
"""
inside_sensor.py

Auto-discovers sensors on any available I2C bus (useful for HyperPixel 4/4 Square
which expose non-standard I2C bus numbers like 13/14/15).

Supported sensors & default addresses:
- SHT4x (e.g., SHT41)        : 0x44 (0x45 alt)   -> temperature (°C), humidity (%)
- BME280                      : 0x76 (0x77 alt)   -> temperature (°C), pressure (hPa), humidity (%)
- LTR559 (ALS/Proximity)      : 0x23              -> light (lux)  [proximity ignored here]
- LSM6DS3 (IMU)               : 0x6a (0x6b alt)   -> detected only (no readings here)

Dependencies (install if missing):
    sudo apt-get install -y python3-smbus
    pip3 install smbus2 ltr559 pimoroni-bme280 lsm6dsox
"""

from __future__ import annotations
import glob
import time
from typing import Dict, Optional, Tuple, List

from smbus2 import SMBus, i2c_msg

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
    from lsm6dsox import LSM6DSOX  # similar API to LSM6DS3 variant; used for presence check fallback
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
