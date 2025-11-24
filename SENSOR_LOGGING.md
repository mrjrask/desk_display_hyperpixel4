# Sensor Logging

The desk display now automatically logs sensor readings to a CSV file in your home directory.

## Log File Location

**`~/sensor_readings.csv`**

The log file is created in your home directory (e.g., `/home/user/sensor_readings.csv`)

## What Gets Logged

The following sensor data is logged whenever the "Inside" screen is displayed:

- **Timestamp**: ISO format date and time
- **Temperature**: In both Celsius and Fahrenheit
- **Humidity**: Percentage
- **Pressure**: In hectopascals (hPa)
- **Light**: Ambient light in lux
- **Proximity**: Proximity sensor reading
- **Accelerometer**: X, Y, Z values in m/s²
- **Gyroscope**: X, Y, Z values in rad/s
- **Pitch/Roll**: In degrees
- **Orientation**: Descriptive label (e.g., "Face up", "Face down")

## Sensors Detected

The system automatically detects and uses the following sensors:

- **SHT4x** (0x44/0x45): High-precision temperature and humidity
- **BME280** (0x76/0x77): Temperature, humidity, and pressure
- **LTR559** (0x23): Ambient light and proximity
- **LSM6DS3/LSM6DSOX** (0x6a/0x6b): Accelerometer and gyroscope (IMU)

## CSV Format

The log file is in standard CSV format with headers, making it easy to:
- Open in Excel or Google Sheets
- Import into data analysis tools
- Process with Python pandas
- Visualize with plotting libraries

## Log File Management

The log file grows over time. To manage it:

```bash
# View recent entries
tail -20 ~/sensor_readings.csv

# View file size
ls -lh ~/sensor_readings.csv

# Archive old logs
mv ~/sensor_readings.csv ~/sensor_readings_backup_$(date +%Y%m%d).csv

# Clear the log (creates new file on next reading)
rm ~/sensor_readings.csv
```

## Testing the Logger

You can test the logging system independently:

```bash
cd /home/user/desk_display_hyperpixel4
python3 sensor_logger.py
```

This will create a sample entry in the log file.
