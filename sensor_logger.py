#!/usr/bin/env python3
"""Simple sensor logging to user's home directory.

Logs sensor readings from draw_inside.py SensorHub to a CSV file in the home folder.
"""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# Log file location in user's home directory
LOG_FILE = Path.home() / "sensor_readings.csv"

# CSV headers for the log file
HEADERS = [
    "timestamp",
    "temperature_c",
    "temperature_f",
    "humidity_pct",
    "pressure_hpa",
    "light_lux",
    "proximity",
    "accel_x_ms2",
    "accel_y_ms2",
    "accel_z_ms2",
    "gyro_x_rads",
    "gyro_y_rads",
    "gyro_z_rads",
    "pitch_deg",
    "roll_deg",
    "orientation",
]


def log_sensor_reading(readings: Dict[str, Any]) -> None:
    """
    Append a sensor reading to the log file.

    Args:
        readings: Dictionary of sensor readings from SensorHub.get_readings()
    """
    # Check if file exists to determine if we need to write headers
    file_exists = LOG_FILE.exists()

    # Extract values from readings dictionary
    temp_c = readings.get("temperature_c")
    temp_f = (temp_c * 9.0 / 5.0 + 32.0) if temp_c is not None else None
    humidity = readings.get("humidity_pct")
    pressure = readings.get("pressure_hpa")
    light = readings.get("light_lux")
    proximity = readings.get("proximity")

    # Extract accelerometer data (tuple of 3 values)
    accel = readings.get("accel_ms2")
    accel_x = accel[0] if accel and len(accel) >= 3 else None
    accel_y = accel[1] if accel and len(accel) >= 3 else None
    accel_z = accel[2] if accel and len(accel) >= 3 else None

    # Extract gyroscope data (tuple of 3 values)
    gyro = readings.get("gyro_rads")
    gyro_x = gyro[0] if gyro and len(gyro) >= 3 else None
    gyro_y = gyro[1] if gyro and len(gyro) >= 3 else None
    gyro_z = gyro[2] if gyro and len(gyro) >= 3 else None

    pitch = readings.get("pitch_deg")
    roll = readings.get("roll_deg")
    orientation = readings.get("orientation_label", "")

    # Prepare row data
    row = [
        datetime.now().isoformat(),
        temp_c,
        temp_f,
        humidity,
        pressure,
        light,
        proximity,
        accel_x,
        accel_y,
        accel_z,
        gyro_x,
        gyro_y,
        gyro_z,
        pitch,
        roll,
        orientation,
    ]

    # Write to CSV file
    try:
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)

            # Write header if this is a new file
            if not file_exists:
                writer.writerow(HEADERS)

            # Write the data row
            writer.writerow(row)

    except Exception as e:
        print(f"Error writing to sensor log: {e}")


def get_log_file_path() -> str:
    """Return the absolute path to the sensor log file."""
    return str(LOG_FILE)


if __name__ == "__main__":
    # Test the logger with sample data
    print(f"Sensor log file location: {LOG_FILE}")

    # Example usage
    sample_readings = {
        "temperature_c": 22.5,
        "humidity_pct": 45.0,
        "pressure_hpa": 1013.25,
        "light_lux": 150.0,
        "proximity": 10,
        "accel_ms2": (0.1, 0.2, 9.8),
        "gyro_rads": (0.01, 0.02, 0.03),
        "pitch_deg": 1.5,
        "roll_deg": 2.3,
        "orientation_label": "Face up",
    }

    log_sensor_reading(sample_readings)
    print(f"Sample reading logged to {LOG_FILE}")
