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

# 3. Check API keys
print("3. API Key Configuration:")
print("-" * 40)
if ssid == "Verano":
    owm_key = os.environ.get("OWM_API_KEY_VERANO") or os.environ.get("OWM_API_KEY")
elif ssid == "wiffy":
    owm_key = os.environ.get("OWM_API_KEY_WIFFY") or os.environ.get("OWM_API_KEY")
else:
    owm_key = os.environ.get("OWM_API_KEY_DEFAULT") or os.environ.get("OWM_API_KEY")

if owm_key:
    print(f"   OpenWeatherMap API Key: {owm_key[:8]}...{owm_key[-4:]}")
    print("   Provider: OpenWeatherMap (primary)")
else:
    print("   OpenWeatherMap API Key: NOT SET")
    print("   Provider: Open-Meteo (fallback)")
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
print(f"API Provider: {'OpenWeatherMap' if owm_key else 'Open-Meteo'}")
print()
print("Run this script on both Pis and compare:")
print("  - If SSIDs differ → Both Pis need same network")
print("  - If coordinates differ → Fix SSID detection")
print("  - If API providers differ → Check API keys")
print("=" * 60)
