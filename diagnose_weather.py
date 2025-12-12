#!/usr/bin/env python3
"""
Diagnostic script to identify why two Raspberry Pis show different weather.
Run this on both Pis and compare the output.
"""
import subprocess
import os
import sys

print("=" * 60)
print("WEATHER SYNC DIAGNOSTIC TOOL")
print("=" * 60)
print()

# 1. Check WiFi SSID
print("1. WiFi Network Detection:")
print("-" * 40)
try:
    ssid = subprocess.check_output(["iwgetid", "-r"]).decode("utf-8").strip()
    print(f"   Current SSID: {ssid}")
except Exception as e:
    print(f"   ERROR detecting SSID: {e}")
    print("   This Pi will use DEFAULT coordinates!")
    ssid = None
print()

# 2. Show which coordinates will be used
print("2. Location Configuration:")
print("-" * 40)
if ssid == "Verano":
    lat, lon = 41.9103, -87.6340
    location = "Chicago Home"
elif ssid == "wiffy":
    lat, lon = 42.13444, -87.876389
    location = "Work Location"
else:
    lat, lon = 41.9103, -87.6340
    location = "Default (Chicago Home)"
print(f"   Location: {location}")
print(f"   Latitude:  {lat}")
print(f"   Longitude: {lon}")
print()

# 3. Check Apple WeatherKit credentials
print("3. WeatherKit Configuration:")
print("-" * 40)
team_id = os.environ.get("WEATHERKIT_TEAM_ID")
key_id = os.environ.get("WEATHERKIT_KEY_ID")
service_id = os.environ.get("WEATHERKIT_SERVICE_ID")
private_key = os.environ.get("WEATHERKIT_PRIVATE_KEY") or os.environ.get("WEATHERKIT_PRIVATE_KEY_PATH")

print(f"   Team ID:      {team_id or 'NOT SET'}")
print(f"   Key ID:       {key_id or 'NOT SET'}")
print(f"   Service ID:   {service_id or 'NOT SET'}")
if private_key:
    if len(private_key) > 40:
        print(f"   Private key:  set (length {len(private_key)} chars)")
    else:
        print("   Private key:  set")
else:
    print("   Private key:  NOT SET")
print()

# 4. Test actual weather fetch
print("4. Testing Weather Fetch:")
print("-" * 40)
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from data_fetch import fetch_weather

    weather = fetch_weather()
    if weather:
        temp = weather.get("current", {}).get("temp")
        desc = weather.get("current", {}).get("weather", [{}])[0].get("description", "N/A")
        print(f"   ✓ Weather fetched successfully")
        print(f"   Temperature: {temp}°F")
        print(f"   Description: {desc}")
    else:
        print(f"   ✗ Failed to fetch weather")
except Exception as e:
    print(f"   ✗ Error testing fetch: {e}")
print()

# 5. Summary
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"SSID: {ssid or 'NOT DETECTED'}")
print(f"Coordinates: {lat}, {lon}")
missing = [name for name, val in [
    ("TEAM_ID", team_id),
    ("KEY_ID", key_id),
    ("SERVICE_ID", service_id),
    ("PRIVATE_KEY", private_key),
] if not val]
if missing:
    status = f"Missing WeatherKit values: {', '.join(missing)}"
else:
    status = "WeatherKit"
print(f"API Provider: {status}")
print()
print("Run this script on both Pis and compare:")
print("  - If SSIDs differ → Both Pis need same network")
print("  - If coordinates differ → Fix SSID detection")
print("  - If API credentials differ → align WeatherKit env vars")
print("=" * 60)
