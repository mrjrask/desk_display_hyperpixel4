# Weather Sync Issue - Diagnosis & Fix

## Problem
Two Raspberry Pis on the same network are showing different weather values.

## Root Cause
The system automatically detects WiFi SSID and uses different GPS coordinates for different networks:
- **"Verano"** network → Chicago home (41.9103, -87.6340)
- **"wiffy"** network → Work location (42.13444, -87.876389)
- **Other/Unknown** → Default to home (41.9103, -87.6340)

If your Pis detect different SSIDs (or one fails to detect), they'll fetch weather for different locations.

## Quick Diagnosis

Run this on **both** Raspberry Pis:
```bash
cd /home/user/desk_display_hyperpixel4
python3 diagnose_weather.py
```

Compare the output from both Pis:
- **SSID** should be identical
- **Coordinates** should be identical
- **API Provider** should be identical

## Solutions

### Option 1: Force Same Coordinates (Recommended)
Override the location using environment variables on **both** Pis:

```bash
# Add to your systemd service or .env file
export LATITUDE=41.9103
export LONGITUDE=-87.6340
```

Then restart the service:
```bash
sudo systemctl restart desk-display  # or whatever your service name is
```

### Option 2: Verify WiFi Connection
Ensure both Pis are on the **exact same** WiFi network:

```bash
# Check current SSID on each Pi
iwgetid -r
```

If different, reconnect to the same network.

### Option 3: Add Your SSID to Config
If your home WiFi isn't "Verano", add it to `config.py`:

```python
if CURRENT_SSID == "Verano":
    # existing code...
elif CURRENT_SSID == "YourActualSSID":  # <-- Add this
    ENABLE_WEATHER = True
    LATITUDE       = 41.9103  # Your coordinates
    LONGITUDE      = -87.6340
    TRAVEL_MODE    = "to_home"
elif CURRENT_SSID == "wiffy":
    # existing code...
```

### Option 4: Use Same WeatherKit Credentials
Ensure both Pis share the exact same WeatherKit environment variables (Team ID, Key ID, Service ID, and private key path/text):
```bash
export WEATHERKIT_TEAM_ID="YOUR_APPLE_TEAM_ID"
export WEATHERKIT_KEY_ID="YOUR_WEATHERKIT_KEY_ID"
export WEATHERKIT_SERVICE_ID="com.example.service"
export WEATHERKIT_PRIVATE_KEY_PATH="/home/pi/AuthKey.p8"
```

## Verification

After applying a fix:

1. **Restart both Pis**
   ```bash
   sudo systemctl restart desk-display
   ```

2. **Check logs** to verify coordinates:
   ```bash
   journalctl -u desk-display -n 50 | grep "Weather location configured"
   ```

   Should show identical output like:
   ```
   Weather location configured: SSID=YourNetwork, Lat=41.9103, Lon=-87.6340 (from environment)
   ```

3. **Run diagnostic again**:
   ```bash
   python3 diagnose_weather.py
   ```

4. **Wait 10 minutes** for both to refresh (weather updates every 10 minutes)

## Still Not Synced?

Check these edge cases:

- **Time drift**: If system clocks differ significantly, cached data expires at different times
  ```bash
  timedatectl  # Check if time is synced
  ```

- **Different update schedules**: One Pi might have restarted recently (fresh data) while the other has old cache
  ```bash
  # Force refresh by restarting both at the same time
  ```

- **Network issues**: One Pi might be failing to fetch and showing old cached data
  ```bash
  # Check logs for fetch errors
  journalctl -u desk-display | grep -i "error.*weather"
  ```

## Changes Made

The fix adds environment variable support to override coordinates:
- `LATITUDE` env var overrides SSID-based latitude
- `LONGITUDE` env var overrides SSID-based longitude
- Logging shows which coordinates are being used on startup

This ensures both Pis can be forced to use the same location regardless of SSID detection.
