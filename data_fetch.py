#!/usr/bin/env python3
"""
data_fetch.py

All remote data fetchers for weather, Blackhawks, MLB, etc.,
with resilient retries via a shared requests.Session.
"""

import csv
import datetime
import io
import logging
import os
import socket
import time
from typing import Optional

import pytz
import requests
import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from services.http_client import NHL_HEADERS, get_session
from screens.nba_scoreboard import _fetch_games_for_date as _nba_fetch_games_for_date

from config import (
    LATITUDE,
    LONGITUDE,
    NHL_API_URL,
    NHL_TEAM_ID,
    MLB_API_URL,
    MLB_CUBS_TEAM_ID,
    MLB_SOX_TEAM_ID,
    CENTRAL_TIME,
    NBA_TEAM_ID,
    NBA_TEAM_TRICODE,
    WEATHERKIT_API_URL,
    WEATHERKIT_KEY_ID,
    WEATHERKIT_LANGUAGE,
    WEATHERKIT_PRIVATE_KEY,
    WEATHERKIT_SERVICE_ID,
    WEATHERKIT_TEAM_ID,
    WEATHER_REFRESH_MINUTES,
    WEATHER_MAX_STALE_MINUTES,
    OWM_API_KEY,
)

# ─── Shared HTTP session ─────────────────────────────────────────────────────
_session = get_session()

# Cache statsapi DNS availability to avoid repeated slow lookups
_statsapi_dns_available: Optional[bool] = None
_statsapi_dns_checked_at: Optional[float] = None
_STATSAPI_DNS_RECHECK_SECONDS = 600

# -----------------------------------------------------------------------------
# WEATHER
# -----------------------------------------------------------------------------
_weather_token: Optional[str] = None
_weather_token_expiration: Optional[datetime.datetime] = None
_OWM_URL = "https://api.openweathermap.org/data/3.0/onecall"
_WEATHER_BACKOFF_UNTIL: dict[str, datetime.datetime] = {}
_WEATHER_BACKOFF_LOGGED: set[str] = set()
_WEATHER_BACKOFF_DEFAULT = datetime.timedelta(minutes=10)
_WEATHER_BACKOFF_RATELIMIT = datetime.timedelta(minutes=90)


def _set_weather_backoff(source: str, until: datetime.datetime):
    _WEATHER_BACKOFF_UNTIL[source] = until
    _WEATHER_BACKOFF_LOGGED.discard(source)


def _clear_weather_backoff(source: str):
    _WEATHER_BACKOFF_UNTIL.pop(source, None)
    _WEATHER_BACKOFF_LOGGED.discard(source)


def _should_skip_weather_source(source: str, now: datetime.datetime) -> bool:
    until = _WEATHER_BACKOFF_UNTIL.get(source)
    if not until:
        return False
    if now >= until:
        _WEATHER_BACKOFF_UNTIL.pop(source, None)
        _WEATHER_BACKOFF_LOGGED.discard(source)
        return False

    if source not in _WEATHER_BACKOFF_LOGGED:
        logging.warning(
            "Skipping %s weather fetch until %s due to previous errors",
            source,
            until.isoformat(),
        )
        _WEATHER_BACKOFF_LOGGED.add(source)
    return True


def load_weatherkit_private_key(key_path: str):
    with open(key_path, "rb") as f:
        pem_bytes = f.read()

    # normalize line endings; ensure trailing newline
    pem_bytes = pem_bytes.replace(b"\r\n", b"\n").strip() + b"\n"

    return serialization.load_pem_private_key(
        pem_bytes,
        password=None,
        backend=default_backend(),
    )


class _ConditionMapping:
    def __init__(self, weather_id: int, main: str, description: str, icon: str):
        self.weather_id = weather_id
        self.main = main
        self.description = description
        self.icon = icon


_CONDITION_MAP: dict[str, _ConditionMapping] = {
    "Blizzard": _ConditionMapping(602, "Snow", "Blizzard", "snow-heavy"),
    "BlowingSnow": _ConditionMapping(601, "Snow", "Blowing snow", "snow"),
    "Breezy": _ConditionMapping(951, "Wind", "Breezy", "wind"),
    "Clear": _ConditionMapping(800, "Clear", "Clear sky", "clear"),
    "Cloudy": _ConditionMapping(803, "Clouds", "Cloudy", "cloudy"),
    "Drizzle": _ConditionMapping(300, "Drizzle", "Drizzle", "drizzle"),
    "Dust": _ConditionMapping(731, "Dust", "Dust", "dust"),
    "Flurries": _ConditionMapping(620, "Snow", "Flurries", "snow"),
    "Fog": _ConditionMapping(741, "Fog", "Fog", "fog"),
    "FreezingDrizzle": _ConditionMapping(301, "Drizzle", "Freezing drizzle", "drizzle"),
    "FreezingRain": _ConditionMapping(511, "Rain", "Freezing rain", "rain-freezing"),
    "Frigid": _ConditionMapping(900, "Extreme", "Frigid", "extreme"),
    "Hail": _ConditionMapping(906, "Hail", "Hail", "hail"),
    "Haze": _ConditionMapping(721, "Haze", "Haze", "haze"),
    "HeavyRain": _ConditionMapping(502, "Rain", "Heavy rain", "rain-heavy"),
    "HeavySnow": _ConditionMapping(602, "Snow", "Heavy snow", "snow-heavy"),
    "Hot": _ConditionMapping(904, "Extreme", "Hot", "extreme"),
    "Hurricane": _ConditionMapping(781, "Extreme", "Hurricane", "storm"),
    "IsolatedThunderstorms": _ConditionMapping(211, "Thunderstorm", "Isolated t-storms", "thunder"),
    "MostlyClear": _ConditionMapping(801, "Clear", "Mostly clear", "mostly-clear"),
    "MostlyCloudy": _ConditionMapping(804, "Clouds", "Mostly cloudy", "cloudy"),
    "PartlyCloudy": _ConditionMapping(802, "Clouds", "Partly cloudy", "partly-cloudy"),
    "Rain": _ConditionMapping(501, "Rain", "Rain", "rain"),
    "ScatteredThunderstorms": _ConditionMapping(210, "Thunderstorm", "Scattered t-storms", "thunder"),
    "Sleet": _ConditionMapping(611, "Snow", "Sleet", "sleet"),
    "Smoke": _ConditionMapping(711, "Smoke", "Smoke", "haze"),
    "Snow": _ConditionMapping(600, "Snow", "Snow", "snow"),
    "StrongStorms": _ConditionMapping(212, "Thunderstorm", "Strong storms", "thunder"),
    "SunFlurries": _ConditionMapping(615, "Snow", "Sun flurries", "snow"),
    "SunShowers": _ConditionMapping(521, "Rain", "Sun showers", "rain"),
    "Thunderstorms": _ConditionMapping(211, "Thunderstorm", "Thunderstorms", "thunder"),
    "Tornado": _ConditionMapping(781, "Extreme", "Tornado", "storm"),
    "Windy": _ConditionMapping(905, "Wind", "Windy", "wind"),
}


def _generate_weatherkit_token() -> Optional[str]:
    global _weather_token, _weather_token_expiration

    if not WEATHERKIT_KEY_ID or not WEATHERKIT_TEAM_ID or not WEATHERKIT_SERVICE_ID:
        logging.error("WeatherKit credentials missing; cannot fetch weather data")
        return None

    key_path = os.environ.get("WEATHERKIT_KEY_PATH")
    signing_key = WEATHERKIT_PRIVATE_KEY

    if key_path:
        try:
            signing_key = load_weatherkit_private_key(key_path)
        except Exception as exc:  # pragma: no cover - depends on filesystem
            logging.error(
                "Failed to load WeatherKit key from WEATHERKIT_KEY_PATH: %s", exc
            )
            return None

    if not signing_key:
        logging.error(
            "WeatherKit private key missing; set WEATHERKIT_KEY_PATH or WEATHERKIT_PRIVATE_KEY"
        )
        return None

    now = datetime.datetime.utcnow()
    if _weather_token and _weather_token_expiration and now < _weather_token_expiration:
        return _weather_token

    headers = {"alg": "ES256", "kid": WEATHERKIT_KEY_ID, "id": f"{WEATHERKIT_TEAM_ID}.{WEATHERKIT_SERVICE_ID}"}
    claims = {
        "iss": WEATHERKIT_TEAM_ID,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=50),
        "sub": WEATHERKIT_SERVICE_ID,
    }

    try:
        _weather_token = jwt.encode(
            claims, signing_key, algorithm="ES256", headers=headers
        )
        _weather_token_expiration = now + datetime.timedelta(minutes=50)
        return _weather_token
    except Exception as exc:
        logging.error("Failed to create WeatherKit token: %s", exc)
        return None


def _convert_temperature(value, unit_hint: Optional[str]):
    if value is None:
        return None
    if unit_hint and unit_hint.lower().startswith("c"):
        return round((float(value) * 9 / 5) + 32, 1)
    try:
        return round(float(value), 1)
    except Exception:
        return None


def _convert_speed(value, unit_hint: Optional[str]):
    if value is None:
        return None
    try:
        val = float(value)
    except Exception:
        return None
    if unit_hint and unit_hint.lower().startswith("kph"):
        return round(val / 1.60934, 1)
    if unit_hint and unit_hint.lower().startswith("mps"):
        return round(val * 2.23694, 1)
    return round(val, 1)


def _convert_humidity(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        humidity = float(value)
    except Exception:
        return None
    if humidity <= 1:
        humidity *= 100
    humidity = round(humidity)
    if humidity < 0:
        humidity = 0
    if humidity > 100:
        humidity = 100
    return int(humidity)


def _dict_section(payload: object, key: str) -> dict:
    if not isinstance(payload, dict):
        return {}
    section = payload.get(key)
    return section if isinstance(section, dict) else {}


def _units_dict(metadata: object) -> dict:
    """WeatherKit sections usually include metadata.units as a dict.
    If it's missing or malformed (e.g., string), return {} so callers
    don't crash on units.get(...).
    """
    if not isinstance(metadata, dict):
        return {}
    units = metadata.get("units")
    return units if isinstance(units, dict) else {}


def _map_condition(code: Optional[str], is_daytime: bool) -> dict:
    if not code:
        return {"description": "Unknown", "icon": None}
    mapping = _CONDITION_MAP.get(code) or _ConditionMapping(800, "Clear", code, "clear")
    suffix = "day" if is_daytime else "night"
    icon_code = f"wk-{(code or mapping.icon)}-{suffix}"
    return {
        "id": mapping.weather_id,
        "main": mapping.main,
        "description": mapping.description,
        "icon": icon_code,
    }


def _map_daily_forecast(payload: dict) -> list[dict]:
    forecast: list[dict] = []
    forecast_daily = _dict_section(payload, "forecastDaily")

    days = forecast_daily.get("days")
    if not isinstance(days, list):
        return forecast

    metadata = forecast_daily.get("metadata")
    units = _units_dict(metadata)

    for day in days:
        if not isinstance(day, dict):
            continue

        condition = _map_condition(day.get("conditionCode"), True)
        forecast.append(
            {
                "dt": day.get("forecastStart"),
                "sunrise": day.get("sunriseTime") or day.get("sunrise"),
                "sunset": day.get("sunsetTime") or day.get("sunset"),
                "temp": {
                    "max": _convert_temperature(day.get("highTemperature"), units.get("temperature")),
                    "min": _convert_temperature(day.get("lowTemperature"), units.get("temperature")),
                },
                "rain": day.get("precipitationAmount"),
                "weather": [condition],
            }
        )

    return forecast


def _map_hourly_forecast(payload: dict) -> list[dict]:
    forecast_hourly = _dict_section(payload, "forecastHourly")

    hours = forecast_hourly.get("hours")
    forecast: list[dict] = []
    if not isinstance(hours, list):
        return forecast

    metadata = forecast_hourly.get("metadata")
    units = _units_dict(metadata)

    for hour in hours:
        if not isinstance(hour, dict):
            continue

        daylight_val = hour.get("daylight")
        is_daytime = bool(daylight_val) if isinstance(daylight_val, bool) else True

        condition = _map_condition(hour.get("conditionCode"), is_daytime)
        forecast.append(
            {
                "dt": hour.get("forecastStart"),
                "temp": _convert_temperature(hour.get("temperature"), units.get("temperature")),
                "feels_like": _convert_temperature(hour.get("temperatureApparent"), units.get("temperature")),
                "humidity": _convert_humidity(hour.get("humidity")),
                "pressure": hour.get("pressure"),
                "wind_speed": _convert_speed(hour.get("windSpeed"), units.get("windSpeed")),
                "wind_deg": hour.get("windDirection"),
                "pop": hour.get("precipitationChance"),
                "uvi": hour.get("uvIndex"),
                "weather": [condition],
            }
        )

    return forecast


def _map_current_weather(payload: dict, daily: list[dict]) -> dict:
    current = _dict_section(payload, "currentWeather")

    metadata = current.get("metadata")
    units = _units_dict(metadata)

    daylight_flag = current.get("isDaylight")
    is_daylight = bool(daylight_flag) if isinstance(daylight_flag, bool) else True

    sunrise = daily[0].get("sunrise") if daily else None
    sunset = daily[0].get("sunset") if daily else None

    condition = _map_condition(current.get("conditionCode"), is_daylight)

    return {
        "dt": current.get("asOf") or current.get("timestamp"),
        "temp": _convert_temperature(current.get("temperature"), units.get("temperature")),
        "feels_like": _convert_temperature(current.get("apparentTemperature"), units.get("temperature")),
        "humidity": _convert_humidity(current.get("humidity")),
        "pressure": current.get("pressure"),
        "wind_speed": _convert_speed(current.get("windSpeed"), units.get("windSpeed")),
        "wind_deg": current.get("windDirection"),
        "uvi": current.get("uvIndex"),
        "sunrise": sunrise,
        "sunset": sunset,
        "weather": [condition],
    }


def _map_alerts(payload: dict) -> list[dict]:
    weather_alerts = _dict_section(payload, "weatherAlerts")
    alerts_blob = weather_alerts.get("alerts") if isinstance(weather_alerts, dict) else []
    alerts: list[dict] = []
    if not isinstance(alerts_blob, list):
        return alerts

    for alert in alerts_blob:
        if not isinstance(alert, dict):
            continue
        alerts.append(
            {
                "event": alert.get("name") or alert.get("severity"),
                "description": alert.get("description") or alert.get("details"),
                "severity": alert.get("severity"),
                "start": alert.get("effectiveTime"),
                "end": alert.get("expirationTime"),
            }
        )
    return alerts


def _map_owm_daily(payload: dict) -> list[dict]:
    forecast: list[dict] = []
    daily = payload.get("daily") if isinstance(payload, dict) else []
    if not isinstance(daily, list):
        return forecast

    for day in daily:
        if not isinstance(day, dict):
            continue
        temps = day.get("temp") if isinstance(day.get("temp"), dict) else {}
        weather_list = day.get("weather") if isinstance(day.get("weather"), list) else []
        condition = weather_list[0] if weather_list else {}
        forecast.append(
            {
                "dt": day.get("dt"),
                "sunrise": day.get("sunrise"),
                "sunset": day.get("sunset"),
                "temp": {
                    "max": _convert_temperature(temps.get("max"), None),
                    "min": _convert_temperature(temps.get("min"), None),
                },
                "rain": day.get("rain"),
                "weather": [condition] if condition else [],
            }
        )
    return forecast


def _map_owm_current(payload: dict, daily: list[dict]) -> dict:
    current = payload.get("current", {}) if isinstance(payload, dict) else {}
    weather_list = current.get("weather") if isinstance(current.get("weather"), list) else []
    condition = weather_list[0] if weather_list else {}
    sunrise = daily[0].get("sunrise") if daily else current.get("sunrise")
    sunset = daily[0].get("sunset") if daily else current.get("sunset")

    return {
        "dt": current.get("dt"),
        "temp": _convert_temperature(current.get("temp"), None),
        "feels_like": _convert_temperature(current.get("feels_like"), None),
        "humidity": current.get("humidity"),
        "pressure": current.get("pressure"),
        "wind_speed": _convert_speed(current.get("wind_speed"), None),
        "wind_deg": current.get("wind_deg"),
        "uvi": current.get("uvi"),
        "sunrise": sunrise,
        "sunset": sunset,
        "weather": [condition] if condition else [],
    }


def _map_owm_hourly(payload: dict) -> list[dict]:
    forecast: list[dict] = []
    hourly = payload.get("hourly") if isinstance(payload, dict) else []
    if not isinstance(hourly, list):
        return forecast

    for hour in hourly:
        if not isinstance(hour, dict):
            continue
        weather_list = hour.get("weather") if isinstance(hour.get("weather"), list) else []
        condition = weather_list[0] if weather_list else {}
        forecast.append(
            {
                "dt": hour.get("dt"),
                "temp": _convert_temperature(hour.get("temp"), None),
                "feels_like": _convert_temperature(hour.get("feels_like"), None),
                "humidity": hour.get("humidity"),
                "pressure": hour.get("pressure"),
                "wind_speed": _convert_speed(hour.get("wind_speed"), None),
                "wind_deg": hour.get("wind_deg"),
                "pop": hour.get("pop"),
                "uvi": hour.get("uvi"),
                "weather": [condition] if condition else [],
            }
        )
    return forecast


def _map_owm_alerts(payload: dict) -> list[dict]:
    alerts_blob = payload.get("alerts") if isinstance(payload, dict) else []
    alerts: list[dict] = []
    if not isinstance(alerts_blob, list):
        return alerts

    for alert in alerts_blob:
        if not isinstance(alert, dict):
            continue
        alerts.append(
            {
                "event": alert.get("event"),
                "description": alert.get("description"),
                "severity": alert.get("severity"),
                "start": alert.get("start"),
                "end": alert.get("end"),
            }
        )
    return alerts


def _fetch_weatherkit(now: datetime.datetime) -> Optional[dict]:
    token = _generate_weatherkit_token()
    if not token:
        return None

    params = {
        "dataSets": "currentWeather,forecastDaily,forecastHourly,weatherAlerts",
        "timezone": "America/Chicago",
    }

    url = f"{WEATHERKIT_API_URL}/{WEATHERKIT_LANGUAGE}/{LATITUDE}/{LONGITUDE}"
    try:
        r = _session.get(
            url,
            params=params,
            timeout=10,
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        payload = r.json()

        if not isinstance(payload, dict):
            logging.error(
                "WeatherKit response is not a JSON object (type %s); suppressing requests for %s minutes",
                type(payload).__name__,
                int(_WEATHER_BACKOFF_DEFAULT.total_seconds() // 60),
            )
            _set_weather_backoff("weatherkit", now + _WEATHER_BACKOFF_DEFAULT)
            return None

        daily = _map_daily_forecast(payload)
        return {
            "lat": LATITUDE,
            "lon": LONGITUDE,
            "daily": daily,
            "hourly": _map_hourly_forecast(payload),
            "current": _map_current_weather(payload, daily),
            "alerts": _map_alerts(payload),
        }
    except requests.exceptions.HTTPError as http_err:
        logging.error("HTTP error fetching WeatherKit data: %s", http_err)
        retry_for = _WEATHER_BACKOFF_RATELIMIT if getattr(http_err.response, "status_code", None) == 429 else _WEATHER_BACKOFF_DEFAULT
        _set_weather_backoff("weatherkit", now + retry_for)
    except Exception as exc:
        logging.error("Error fetching WeatherKit data: %s", exc)
        _set_weather_backoff("weatherkit", now + _WEATHER_BACKOFF_DEFAULT)

    return None


def _fetch_openweathermap(now: datetime.datetime) -> Optional[dict]:
    if not OWM_API_KEY:
        logging.warning(
            "OpenWeatherMap API key missing; skipping backup weather fetch"
        )
        return None

    params = {
        "lat": LATITUDE,
        "lon": LONGITUDE,
        "appid": OWM_API_KEY,
        "units": "imperial",
        "lang": WEATHERKIT_LANGUAGE,
        "exclude": "minutely",
    }

    try:
        r = _session.get(_OWM_URL, params=params, timeout=10)
        r.raise_for_status()
        payload = r.json()

        if not isinstance(payload, dict):
            logging.error(
                "OpenWeatherMap response is not a JSON object (type %s); suppressing requests for %s minutes",
                type(payload).__name__,
                int(_WEATHER_BACKOFF_DEFAULT.total_seconds() // 60),
            )
            _set_weather_backoff("openweathermap", now + _WEATHER_BACKOFF_DEFAULT)
            return None

        daily = _map_owm_daily(payload)
        return {
            "lat": payload.get("lat", LATITUDE),
            "lon": payload.get("lon", LONGITUDE),
            "daily": daily,
            "hourly": _map_owm_hourly(payload),
            "current": _map_owm_current(payload, daily),
            "alerts": _map_owm_alerts(payload),
        }
    except requests.exceptions.HTTPError as http_err:
        status = getattr(http_err.response, "status_code", None)
        if status == 429:
            logging.error(
                "HTTP error fetching OpenWeatherMap data: %s (suppressing for %s minutes)",
                http_err,
                int(_WEATHER_BACKOFF_RATELIMIT.total_seconds() // 60),
            )
            _set_weather_backoff("openweathermap", now + _WEATHER_BACKOFF_RATELIMIT)
        else:
            logging.error("HTTP error fetching OpenWeatherMap data: %s", http_err)
            _set_weather_backoff("openweathermap", now + _WEATHER_BACKOFF_DEFAULT)
    except Exception as exc:
        logging.error("Error fetching OpenWeatherMap data: %s", exc)
        _set_weather_backoff("openweathermap", now + _WEATHER_BACKOFF_DEFAULT)

    return None


def fetch_weather():
    """Fetch weather from WeatherKit with OpenWeatherMap fallback."""

    if not hasattr(fetch_weather, "_last_success"):
        fetch_weather._last_success = None  # type: ignore[attr-defined]
        fetch_weather._last_fetched = None  # type: ignore[attr-defined]

    now = datetime.datetime.utcnow()
    max_stale = datetime.timedelta(minutes=WEATHER_MAX_STALE_MINUTES)
    last_fetched = getattr(fetch_weather, "_last_fetched", None)  # type: ignore[attr-defined]
    last_success = getattr(fetch_weather, "_last_success", None)  # type: ignore[attr-defined]
    if last_fetched and now - last_fetched < datetime.timedelta(minutes=WEATHER_REFRESH_MINUTES):
        return fetch_weather._last_success  # type: ignore[attr-defined]

    for source, fetcher in (("weatherkit", _fetch_weatherkit), ("openweathermap", _fetch_openweathermap)):
        if _should_skip_weather_source(source, now):
            continue

        mapped = fetcher(now)
        if mapped:
            _clear_weather_backoff(source)
            fetch_weather._last_success = mapped  # type: ignore[attr-defined]
            fetch_weather._last_fetched = now  # type: ignore[attr-defined]
            return mapped

    if last_success and last_fetched:
        age = now - last_fetched
        if age <= max_stale:
            return last_success
        logging.warning(
            "Weather data is stale (age %s > %s); discarding cached result",
            age,
            max_stale,
        )

    return None


# -----------------------------------------------------------------------------
# NHL — Blackhawks
# -----------------------------------------------------------------------------
def fetch_blackhawks_next_game():
    try:
        r = _session.get(NHL_API_URL, timeout=10, headers=NHL_HEADERS)
        r.raise_for_status()
        games = r.json().get("games", [])
        fut   = [g for g in games if g.get("gameState") == "FUT"]

        for g in fut:
            if not g.get("startTimeCentral"):
                utc = g.get("startTimeUTC")
                if utc:
                    dt = datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
                    dt = dt.replace(tzinfo=pytz.utc).astimezone(CENTRAL_TIME)
                    g["startTimeCentral"] = dt.strftime("%I:%M %p").lstrip("0")
                else:
                    g["startTimeCentral"] = "TBD"

        fut.sort(key=lambda g: g.get("gameDate", ""))
        return fut[0] if fut else None

    except Exception as e:
        logging.error("Error fetching next Blackhawks game: %s", e)
        return None


def _extract_team_value(team, *keys):
    """Return the first string value found for the provided keys."""
    if not isinstance(team, dict):
        return ""
    for key in keys:
        value = team.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for subkey in ("default", "en", "fullName"):
                subval = value.get(subkey)
                if isinstance(subval, str) and subval.strip():
                    return subval.strip()
    return ""


def _is_blackhawks_team(team):
    if not isinstance(team, dict):
        return False
    if isinstance(team.get("team"), dict):
        team = team["team"]
    team_id = team.get("id") or team.get("teamId")
    if team_id == NHL_TEAM_ID:
        return True
    name = _extract_team_value(team, "commonName", "name", "teamName", "clubName")
    return "blackhawks" in name.lower() if name else False


def _team_id(team):
    if not isinstance(team, dict):
        return None
    if isinstance(team.get("team"), dict):
        return _team_id(team["team"])
    return team.get("id") or team.get("teamId")


def _same_game(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    for key in ("id", "gamePk", "gameId", "gameUUID"):
        av = a.get(key)
        bv = b.get(key)
        if av and bv and av == bv:
            return True
    a_date = a.get("gameDate")
    b_date = b.get("gameDate")
    if a_date and b_date and a_date == b_date:
        a_home = _team_id(a.get("homeTeam") or a.get("home_team") or {})
        b_home = _team_id(b.get("homeTeam") or b.get("home_team") or {})
        a_away = _team_id(a.get("awayTeam") or a.get("away_team") or {})
        b_away = _team_id(b.get("awayTeam") or b.get("away_team") or {})
        return a_home == b_home and a_away == b_away
    return False


# -----------------------------------------------------------------------------
# NBA — Chicago Bulls
# -----------------------------------------------------------------------------
_BULLS_TEAM_ID = str(NBA_TEAM_ID)
_BULLS_TRICODE = (NBA_TEAM_TRICODE or "CHI").upper()
_NBA_LOOKBACK_DAYS = 7
_NBA_LOOKAHEAD_DAYS = 45
_NBA_STANDINGS_BACKOFF_UNTIL: Optional[datetime.datetime] = None
_NBA_STANDINGS_BACKOFF_LOGGED = False


def _parse_nba_datetime(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            parsed = datetime.datetime.strptime(text, fmt)
        except Exception:
            continue
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(CENTRAL_TIME)
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(CENTRAL_TIME)


def _copy_nba_team(entry):
    if not isinstance(entry, dict):
        return {}
    cloned = dict(entry)
    team_info = cloned.get("team")
    if isinstance(team_info, dict):
        cloned["team"] = dict(team_info)
    return cloned


def _augment_nba_game(game):
    if not isinstance(game, dict):
        return None
    cloned = dict(game)
    teams = cloned.get("teams")
    if isinstance(teams, dict):
        cloned_teams = {}
        for side in ("home", "away"):
            cloned_teams[side] = _copy_nba_team(teams.get(side) or {})
        cloned["teams"] = cloned_teams
    start_local = cloned.get("_start_local")
    if not isinstance(start_local, datetime.datetime):
        start_local = _parse_nba_datetime(cloned.get("gameDate"))
    if isinstance(start_local, datetime.datetime):
        cloned["_start_local"] = start_local
        cloned["officialDate"] = start_local.date().isoformat()
    else:
        date_text = (cloned.get("officialDate") or cloned.get("gameDate") or "").strip()
        cloned["officialDate"] = date_text[:10]
    return cloned


def _is_bulls_team(entry):
    if not isinstance(entry, dict):
        return False
    team_info = entry.get("team") if isinstance(entry.get("team"), dict) else entry
    team_id = str(team_info.get("id") or team_info.get("teamId") or "")
    if team_id and team_id == _BULLS_TEAM_ID:
        return True
    tri = str(team_info.get("triCode") or team_info.get("abbreviation") or "").upper()
    return tri == _BULLS_TRICODE if tri else False


def _is_bulls_game(game):
    if not isinstance(game, dict):
        return False
    teams = game.get("teams") or {}
    return _is_bulls_team(teams.get("home")) or _is_bulls_team(teams.get("away"))


def _nba_game_state(game):
    status = game.get("status") or {}
    abstract = str(status.get("abstractGameState") or "").lower()
    if abstract:
        return abstract
    detailed = str(status.get("detailedState") or "").lower()
    if "final" in detailed:
        return "final"
    if "live" in detailed or "progress" in detailed:
        return "live"
    if "preview" in detailed or "schedule" in detailed or "pregame" in detailed:
        return "preview"
    code = str(status.get("statusCode") or "")
    if code == "3":
        return "final"
    if code == "2":
        return "live"
    if code == "1":
        return "preview"
    return detailed


def _get_bulls_games_for_day(day):
    try:
        games = _nba_fetch_games_for_date(day)
    except Exception as exc:
        logging.error("Failed to fetch NBA scoreboard for %s: %s", day, exc)
        return []
    results = []
    for game in games or []:
        if not _is_bulls_game(game):
            continue
        augmented = _augment_nba_game(game)
        if augmented:
            results.append(augmented)
    return results


def _future_bulls_games(days_forward):
    today = datetime.datetime.now(CENTRAL_TIME).date()
    for delta in range(0, days_forward + 1):
        day = today + datetime.timedelta(days=delta)
        for game in _get_bulls_games_for_day(day):
            yield game


def _past_bulls_games(days_back):
    today = datetime.datetime.now(CENTRAL_TIME).date()
    for delta in range(0, days_back + 1):
        day = today - datetime.timedelta(days=delta)
        games = _get_bulls_games_for_day(day)
        for game in reversed(games):
            yield game


def fetch_bulls_next_game():
    try:
        for game in _future_bulls_games(_NBA_LOOKAHEAD_DAYS):
            if _nba_game_state(game) in {"preview", "scheduled", "pregame"}:
                return game
    except Exception as exc:
        logging.error("Error fetching next Bulls game: %s", exc)
    return None


def fetch_bulls_next_home_game():
    try:
        fallback_game = None
        for game in _future_bulls_games(_NBA_LOOKAHEAD_DAYS):
            teams = game.get("teams") or {}
            if not _is_bulls_team(teams.get("home")):
                continue

            state = _nba_game_state(game)
            if state in {"preview", "scheduled", "pregame"}:
                return game
            if fallback_game is None and state not in {"final", "postponed"}:
                fallback_game = game
        return fallback_game
    except Exception as exc:
        logging.error("Error fetching next Bulls home game: %s", exc)
    return None


def fetch_bulls_last_game():
    try:
        for game in _past_bulls_games(_NBA_LOOKBACK_DAYS):
            if _nba_game_state(game) == "final":
                return game
    except Exception as exc:
        logging.error("Error fetching last Bulls game: %s", exc)
    return None


def fetch_bulls_live_game():
    try:
        for game in _future_bulls_games(0):
            if _nba_game_state(game) == "live":
                return game
        for game in _past_bulls_games(1):
            if _nba_game_state(game) == "live":
                return game
    except Exception as exc:
        logging.error("Error fetching live Bulls game: %s", exc)
    return None


def fetch_blackhawks_next_home_game():
    try:
        next_game = fetch_blackhawks_next_game()
        r = _session.get(NHL_API_URL, timeout=10, headers=NHL_HEADERS)
        r.raise_for_status()
        games = r.json().get("games", [])
        home  = []
        skipped_duplicate = False

        for g in games:
            if g.get("gameState") != "FUT":
                continue
            team = g.get("homeTeam", {}) or g.get("home_team", {})
            if _is_blackhawks_team(team):
                if next_game and _same_game(next_game, g):
                    skipped_duplicate = True
                    continue
                utc = g.get("startTimeUTC")
                if utc:
                    dt = datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
                    dt = dt.replace(tzinfo=pytz.utc).astimezone(CENTRAL_TIME)
                    g["startTimeCentral"] = dt.strftime("%I:%M %p").lstrip("0")
                else:
                    g["startTimeCentral"] = "TBD"
                home.append(g)

        home.sort(key=lambda g: g.get("gameDate", ""))
        if not home:
            if skipped_duplicate:
                logging.info(
                    "Next home Blackhawks game matches the next scheduled game; suppressing duplicate screen."
                )
            else:
                logging.info("No upcoming additional Blackhawks home games were found.")
        return home[0] if home else None

    except Exception as e:
        logging.error("Error fetching next home Blackhawks game: %s", e)
        return None


def fetch_blackhawks_last_game():
    try:
        r = _session.get(NHL_API_URL, timeout=10, headers=NHL_HEADERS)
        r.raise_for_status()
        data  = r.json()
        games = []

        if "dates" in data:
            for di in data["dates"]:
                games.extend(di.get("games", []))
        else:
            games = data.get("games", [])

        offs = [g for g in games if g.get("gameState") == "OFF"]
        if offs:
            offs.sort(key=lambda g: g.get("gameDate", ""))
            return offs[-1]
        return None

    except Exception as e:
        logging.error("Error fetching last Blackhawks game: %s", e)
        return None


def fetch_blackhawks_live_game():
    try:
        r = _session.get(NHL_API_URL, timeout=10, headers=NHL_HEADERS)
        r.raise_for_status()
        games = r.json().get("games", [])
        for g in games:
            state = g.get("gameState", "").lower()
            if state in ("live", "in progress"):
                if not g.get("startTimeCentral"):
                    utc = g.get("startTimeUTC")
                    if utc:
                        dt = datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
                        dt = dt.replace(tzinfo=pytz.utc).astimezone(CENTRAL_TIME)
                        g["startTimeCentral"] = dt.strftime("%I:%M %p").lstrip("0")
                    else:
                        g["startTimeCentral"] = "TBD"
                return g
        return None

    except Exception as e:
        logging.error("Error fetching live Blackhawks game: %s", e)
        return None


# -----------------------------------------------------------------------------
# MLB — schedule helper + Cubs/Sox wrappers
# -----------------------------------------------------------------------------
def _fetch_mlb_schedule(team_id):
    try:
        today = datetime.datetime.now(CENTRAL_TIME).date()
        start = today - datetime.timedelta(days=3)
        end   = today + datetime.timedelta(days=30)

        url = (
            f"{MLB_API_URL}"
            f"?sportId=1&teamId={team_id}"
            f"&startDate={start}&endDate={end}&hydrate=team,linescore"
        )
        r = _session.get(url, timeout=10)
        r.raise_for_status()
        data   = r.json()
        result = {
            "next_game": None,
            "next_home_game": None,
            "live_game": None,
            "last_game": None,
        }
        finished = []
        home_candidates = []
        skipped_home_duplicate = False
        team_id_int = int(team_id)

        for di in data.get("dates", []):
            day = datetime.datetime.strptime(di["date"], "%Y-%m-%d").date()
            for g in di.get("games", []):
                # Convert UTC to Central
                utc = g.get("gameDate")
                local_dt = None
                if utc:
                    dt = datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")
                    dt = dt.replace(tzinfo=pytz.utc).astimezone(CENTRAL_TIME)
                    g["startTimeCentral"] = dt.strftime("%I:%M %p").lstrip("0")
                    local_dt = dt
                else:
                    g["startTimeCentral"] = "TBD"
                    try:
                        local_dt = CENTRAL_TIME.localize(
                            datetime.datetime.combine(day, datetime.time(12, 0))
                        )
                    except Exception:
                        local_dt = None

                # Determine game state
                status      = g.get("status", {})
                code        = status.get("statusCode", "").upper()
                abstract    = status.get("abstractGameState", "").lower()
                detailed    = status.get("detailedState", "").lower()

                # Track upcoming home games for dedicated screen
                home_team_id = (
                    ((g.get("teams") or {}).get("home") or {}).get("team", {})
                ).get("id")
                is_home_game = False
                try:
                    is_home_game = int(home_team_id) == team_id_int
                except Exception:
                    is_home_game = False

                if is_home_game and local_dt and local_dt.date() >= today:
                    is_scheduled = code in {"S", "I"} or abstract in {
                        "preview",
                        "scheduled",
                        "live",
                    } or "progress" in detailed
                    is_postponed = any(
                        kw in detailed for kw in ("postponed", "suspended")
                    )
                    if is_scheduled and not is_postponed:
                        home_candidates.append((local_dt, g))

                # Live game
                if code == "I" or abstract == "live" or "progress" in detailed:
                    result["live_game"] = g

                # Next game (today scheduled)
                if day == today and (code == "S" or abstract in ("preview","scheduled")):
                    result["next_game"] = g

                # Finished up to today
                if day <= today and code not in ("S","I") and abstract not in ("preview","scheduled","live"):
                    finished.append(g)

        # Fallback next future
        if not result["next_game"]:
            for di in data.get("dates", []):
                day = datetime.datetime.strptime(di["date"], "%Y-%m-%d").date()
                if day > today:
                    for g in di.get("games", []):
                        status   = g.get("status", {})
                        code2    = status.get("statusCode", "").upper()
                        abs2     = status.get("abstractGameState", "").lower()
                        if code2 == "S" or abs2 in ("preview","scheduled"):
                            result["next_game"] = g
                            break
                    if result["next_game"]:
                        break

        # Pick earliest upcoming home game
        if home_candidates:
            home_candidates.sort(key=lambda item: item[0])

            next_game_pk = None
            if result["next_game"]:
                next_game_pk = result["next_game"].get("gamePk")

            for _, home_game in home_candidates:
                # If the upcoming game is already a home game, skip duplicating it
                if next_game_pk and home_game.get("gamePk") == next_game_pk:
                    skipped_home_duplicate = True
                    continue
                if (
                    result["next_game"]
                    and home_game.get("gameDate") == result["next_game"].get("gameDate")
                ):
                    skipped_home_duplicate = True
                    continue

                result["next_home_game"] = home_game
                break

        if not result["next_home_game"] and skipped_home_duplicate:
            logging.info(
                "Next MLB home game for team %s matches the upcoming game; suppressing duplicate home screen.",
                team_id,
            )

        # Pick last finished
        if finished:
            finished.sort(key=lambda x: x.get("officialDate",""))
            result["last_game"] = finished[-1]

        return result

    except Exception as e:
        logging.error("Error fetching MLB schedule for %s: %s", team_id, e)
        return {
            "next_game": None,
            "next_home_game": None,
            "live_game": None,
            "last_game": None,
        }


def fetch_cubs_games():
    return _fetch_mlb_schedule(MLB_CUBS_TEAM_ID)


def fetch_sox_games():
    return _fetch_mlb_schedule(MLB_SOX_TEAM_ID)


# -----------------------------------------------------------------------------
# Team standings — helpers shared by NFL / NHL / NBA
# -----------------------------------------------------------------------------
def _safe_int(value):
    try:
        return int(value)
    except Exception:
        return value


def _format_streak_code(prefix, count):
    try:
        c = int(count)
    except Exception:
        return "-"
    if c <= 0:
        return "-"
    return f"{prefix}{c}"


def _format_streak_from_dict(streak_blob):
    if not isinstance(streak_blob, dict):
        return "-"
    prefix = streak_blob.get("type") or streak_blob.get("streakType")
    count = streak_blob.get("count") or streak_blob.get("streakNumber")
    if isinstance(prefix, str):
        prefix = prefix[:1].upper()
    return _format_streak_code(prefix or "-", count)


def _build_split_record(split_type, wins, losses):
    return {"type": split_type, "wins": wins, "losses": losses}


def _extract_split_records(**kwargs):
    splits = []
    for key, value in kwargs.items():
        if not value:
            continue
        wins = value.get("wins")
        losses = value.get("losses")
        if wins is None and losses is None:
            continue
        splits.append(_build_split_record(key, wins, losses))
    return splits


def _empty_standings_record(team_abbr: str) -> dict:
    """Return a placeholder standings structure so screens can still render."""

    return {
        "leagueRecord": {"wins": "-", "losses": "-", "pct": "-"},
        "divisionRank": "-",
        "divisionGamesBack": "-",
        "wildCardGamesBack": None,
        "streak": {"streakCode": "-"},
        "records": {"splitRecords": []},
        "points": None,
        "team": team_abbr,
    }


def _statsapi_available() -> bool:
    """Lightweight DNS check so we avoid slow statsapi fallbacks when DNS fails."""

    global _statsapi_dns_available, _statsapi_dns_checked_at

    now = time.time()
    if _statsapi_dns_checked_at and (now - _statsapi_dns_checked_at) < _STATSAPI_DNS_RECHECK_SECONDS:
        return bool(_statsapi_dns_available)

    try:
        socket.getaddrinfo("statsapi.web.nhl.com", 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        logging.debug("NHL statsapi DNS lookup failed: %s", exc)
        _statsapi_dns_available = False
    except Exception as exc:
        logging.debug("Unexpected error checking NHL statsapi DNS: %s", exc)
        _statsapi_dns_available = False
    else:
        _statsapi_dns_available = True

    _statsapi_dns_checked_at = now
    return bool(_statsapi_dns_available)


# -----------------------------------------------------------------------------
# MLB — standings helper + Cubs/Sox wrappers
# -----------------------------------------------------------------------------
def _fetch_mlb_standings(league_id, division_id, team_id):
    try:
        url = (
            "https://statsapi.mlb.com/api/v1/standings"
            f"?season=2025&leagueId={league_id}&divisionId={division_id}"
        )
        r = _session.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        for rec in data.get("records", []):
            for tr in rec.get("teamRecords", []):
                if tr.get("team", {}).get("id") == int(team_id):
                    return tr

        logging.warning("Team %s not found in standings (L%d/D%d)", team_id, league_id, division_id)
        return None

    except Exception as e:
        logging.error("Error fetching standings for team %s: %s", team_id, e)
        return None


def fetch_cubs_standings():
    return _fetch_mlb_standings(104, 205, MLB_CUBS_TEAM_ID)


def fetch_sox_standings():
    return _fetch_mlb_standings(103, 202, MLB_SOX_TEAM_ID)


# -----------------------------------------------------------------------------
# NFL — Bears standings
# -----------------------------------------------------------------------------
def _fetch_nfl_team_standings(team_abbr: str):
    try:
        url = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/standings.csv"
        resp = _session.get(url, timeout=10)
        resp.raise_for_status()
        entries = [row for row in csv.DictReader(io.StringIO(resp.text)) if row.get("team") == team_abbr]
        if not entries:
            logging.warning("Team %s not found in NFL standings", team_abbr)
            return None

        latest = max(entries, key=lambda r: r.get("season", "0"))
        wins = _safe_int(latest.get("wins"))
        losses = _safe_int(latest.get("losses"))
        ties = _safe_int(latest.get("ties"))

        record = {
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "pct": latest.get("pct"),
        }

        return {
            "leagueRecord": record,
            "divisionRank": latest.get("div_rank") or latest.get("divRank") or "-",
            "division": latest.get("division"),
            "streak": {"streakCode": "-"},
            "records": {"splitRecords": []},
        }
    except Exception as exc:
        logging.error("Error fetching NFL standings for %s: %s", team_abbr, exc)
        return None


def fetch_bears_standings():
    return _fetch_nfl_team_standings("CHI")


# -----------------------------------------------------------------------------
# NHL — Blackhawks standings
# -----------------------------------------------------------------------------
def _fetch_nhl_team_standings(team_abbr: str):
    try:
        url = "https://api-web.nhle.com/v1/standings/now"
        resp = _session.get(url, timeout=10, headers=NHL_HEADERS)
        resp.raise_for_status()
        payload = resp.json() or {}
        standings = payload.get("standings", []) or []
        entry = next((row for row in standings if row.get("teamAbbrev") == team_abbr), None)
        if entry:
            record = {
                "wins": _safe_int(entry.get("wins")),
                "losses": _safe_int(entry.get("losses")),
                "ot": _safe_int(entry.get("otLosses")),
                "pct": entry.get("pointsPctg"),
            }

            home = {"wins": entry.get("homeWins"), "losses": entry.get("homeLosses")}
            away = {"wins": entry.get("roadWins"), "losses": entry.get("roadLosses")}
            l10 = {"wins": entry.get("l10Wins"), "losses": entry.get("l10Losses")}
            division = {
                "wins": entry.get("divisionWins"),
                "losses": entry.get("divisionLosses"),
            }
            conference = {
                "wins": entry.get("conferenceWins"),
                "losses": entry.get("conferenceLosses"),
            }

            splits = _extract_split_records(
                home=home, away=away, lastTen=l10, division=division, conference=conference
            )

            streak_code = entry.get("streakCode") or _format_streak_code(entry.get("streakType"), entry.get("streakNumber"))

            return {
                "leagueRecord": record,
                "divisionRank": entry.get("divisionSeq") or entry.get("divisionRank"),
                "divisionGamesBack": None,
                "wildCardGamesBack": None,
                "streak": {"streakCode": streak_code or "-"},
                "records": {"splitRecords": splits},
                "points": entry.get("points"),
                "conferenceRank": entry.get("conferenceSeq")
                or entry.get("conferenceRank"),
                "conferenceName": entry.get("conferenceName")
                or entry.get("conferenceAbbrev"),
            }
        logging.warning("Team %s not found in NHL standings; trying fallback", team_abbr)
    except Exception as exc:
        logging.error("Error fetching NHL standings for %s: %s", team_abbr, exc)
    fallback = _fetch_nhl_team_standings_espn(team_abbr)
    if fallback:
        return fallback
    if not _statsapi_available():
        logging.info("Skipping statsapi NHL standings fallback due to DNS failure")
        return None
    return _fetch_nhl_team_standings_statsapi(team_abbr)


def fetch_blackhawks_standings():
    return _fetch_nhl_team_standings("CHI")


def _fetch_nhl_team_standings_espn(team_abbr: str):
    """Fallback to ESPN standings when NHL endpoints are unavailable."""

    def _iter_entries(node):
        if not isinstance(node, dict):
            return
        standings = node.get("standings", {})
        for entry in standings.get("entries", []) or []:
            yield entry
        for child in node.get("children", []) or []:
            yield from _iter_entries(child)

    def _stat(stats, name, default=None):
        for stat in stats or []:
            if stat.get("name") == name:
                if stat.get("value") is not None:
                    return stat.get("value")
                return stat.get("displayValue") or stat.get("summary")
        return default

    try:
        url = "https://site.web.api.espn.com/apis/v2/sports/hockey/nhl/standings"
        resp = _session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json() or {}

        for entry in _iter_entries(data):
            team = entry.get("team", {}) or {}
            if (team.get("abbreviation") or team.get("shortDisplayName")) != team_abbr:
                continue

            stats = entry.get("stats") or []
            streak_code = _stat(stats, "streak", "-")
            pct = _stat(stats, "winPercent")
            try:
                pct = float(pct)
            except Exception:
                pass

            logging.info("Using ESPN NHL standings fallback for %s", team_abbr)
            return {
                "leagueRecord": {
                    "wins": _safe_int(_stat(stats, "wins")),
                    "losses": _safe_int(_stat(stats, "losses")),
                    "ot": _safe_int(_stat(stats, "otLosses")),
                    "pct": pct,
                },
                "divisionRank": _stat(stats, "divisionWinPercent")
                or _stat(stats, "playoffSeed"),
                "divisionGamesBack": _stat(stats, "divisionGamesBehind"),
                "wildCardGamesBack": None,
                "streak": {"streakCode": streak_code or "-"},
                "records": {"splitRecords": []},
                "points": _stat(stats, "points"),
                "conferenceRank": _stat(stats, "playoffSeed"),
            }
    except Exception as exc:
        logging.error("Error fetching NHL standings (ESPN fallback) for %s: %s", team_abbr, exc)
    return None


def _fetch_nhl_team_standings_statsapi(team_abbr: str):
    try:
        url = "https://statsapi.web.nhl.com/api/v1/standings"
        resp = _session.get(url, timeout=10, headers=NHL_HEADERS)
        resp.raise_for_status()
        payload = resp.json() or {}
        for record in payload.get("records", []) or []:
            for team in record.get("teamRecords", []) or []:
                info = team.get("team", {}) or {}
                abbr = info.get("abbreviation") or info.get("teamName")
                if abbr != team_abbr:
                    continue

                league_record = team.get("leagueRecord", {}) or {}
                streak = team.get("streak", {}) or {}
                streak_code = streak.get("streakCode") or _format_streak_code(
                    streak.get("streakType"), streak.get("streakNumber")
                )

                split_records = []
                for split in (team.get("records") or {}).get("splitRecords", []) or []:
                    wins = split.get("wins")
                    losses = split.get("losses")
                    if wins is None and losses is None:
                        continue
                    split_records.append(
                        {"type": split.get("type"), "wins": wins, "losses": losses}
                    )

                logging.info("Using statsapi NHL standings fallback for %s", team_abbr)
                return {
                    "leagueRecord": {
                        "wins": _safe_int(league_record.get("wins")),
                        "losses": _safe_int(league_record.get("losses")),
                        "ot": _safe_int(league_record.get("ot")),
                        "pct": league_record.get("pct") or league_record.get("pointsPercentage"),
                    },
                    "divisionRank": team.get("divisionRank"),
                    "divisionGamesBack": team.get("divisionGamesBack"),
                    "wildCardGamesBack": team.get("wildCardRank"),
                    "streak": {"streakCode": streak_code or "-"},
                    "records": {"splitRecords": split_records},
                    "points": team.get("points"),
                    "conferenceRank": team.get("conferenceRank"),
                }
        logging.error("Team %s not found in NHL standings (statsapi fallback)", team_abbr)
    except Exception as exc:
        logging.error("Error fetching NHL standings (statsapi) for %s: %s", team_abbr, exc)
    return None


# -----------------------------------------------------------------------------
# NBA — Bulls standings
# -----------------------------------------------------------------------------
def _fetch_nba_team_standings(team_tricode: str):
    global _NBA_STANDINGS_BACKOFF_UNTIL, _NBA_STANDINGS_BACKOFF_LOGGED

    now = datetime.datetime.utcnow()
    if _NBA_STANDINGS_BACKOFF_UNTIL and now < _NBA_STANDINGS_BACKOFF_UNTIL:
        if not _NBA_STANDINGS_BACKOFF_LOGGED:
            logging.warning(
                "Skipping NBA standings feed until %s; using ESPN fallback",
                _NBA_STANDINGS_BACKOFF_UNTIL.isoformat(),
            )
            _NBA_STANDINGS_BACKOFF_LOGGED = True
        fallback = _fetch_nba_team_standings_espn()
        if fallback:
            return fallback
        logging.warning(
            "NBA standings feed unavailable and ESPN fallback failed; returning placeholder"
        )
        return _empty_standings_record(team_tricode)

    _NBA_STANDINGS_BACKOFF_LOGGED = False

    def _load_json() -> Optional[dict]:
        nonlocal now
        for base in (
            "https://cdn.nba.com/static/json/liveData/standings",
            "https://nba-prod-us-east-1-media.s3.amazonaws.com/json/liveData/standings",
        ):
            url = f"{base}/league.json"
            try:
                resp = _session.get(
                    url,
                    timeout=10,
                    headers={
                        "Origin": "https://www.nba.com",
                        "Referer": "https://www.nba.com/",
                    },
                )
                if resp.status_code == 403:
                    logging.warning("NBA standings returned HTTP 403 from %s", base)
                    continue
                resp.raise_for_status()
                data = resp.json() or {}
                if data and base.endswith("s3.amazonaws.com/json/liveData/standings"):
                    logging.info(
                        "NBA standings fetched successfully from alternate base %s", base
                    )
                _NBA_STANDINGS_BACKOFF_UNTIL = None
                _NBA_STANDINGS_BACKOFF_LOGGED = False
                return data
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 403:
                    _NBA_STANDINGS_BACKOFF_UNTIL = now + datetime.timedelta(minutes=30)
                    _NBA_STANDINGS_BACKOFF_LOGGED = False
                    logging.warning(
                        "NBA standings returned HTTP 403 from %s; suppressing until %s",
                        base,
                        _NBA_STANDINGS_BACKOFF_UNTIL.isoformat(),
                    )
                    return None

                logging.error("Error fetching NBA standings from %s: %s", base, exc)
        return None

    payload = _load_json() or {}
    teams = payload.get("league", {}).get("standard", {}).get("teams", [])

    try:
        entry = next((row for row in teams if row.get("teamTricode") == team_tricode), None)
        if entry:
            record = {
                "wins": _safe_int(entry.get("wins") or entry.get("win")),
                "losses": _safe_int(entry.get("losses") or entry.get("loss")),
                "pct": entry.get("winPct"),
            }

            streak_blob = entry.get("streak") or {}
            streak_code = entry.get("streakText") or entry.get("streakCode")
            if not streak_code:
                streak_code = _format_streak_from_dict(streak_blob)

            division_gb = (
                entry.get("gamesBehind")
                or entry.get("gamesBehindConference")
                or entry.get("gamesBehindConf")
                or entry.get("gamesBehindDivision")
            )

            conference_rank = (
                entry.get("confRank")
                or entry.get("playoffRank")
                or (entry.get("teamConference") or {}).get("rank")
                or entry.get("playoffSeed")
            )

            splits = _extract_split_records(
                lastTen=entry.get("lastTen"),
                home=entry.get("home"),
                away=entry.get("away"),
            )

            return {
                "leagueRecord": record,
                "divisionRank": entry.get("divisionRank")
                or (entry.get("teamDivision") or {}).get("rank")
                or conference_rank,
                "divisionGamesBack": division_gb,
                "wildCardGamesBack": None,
                "streak": {"streakCode": streak_code or "-"},
                "records": {"splitRecords": splits},
                "conferenceRank": conference_rank,
            }
        logging.warning("Team %s not found in NBA standings", team_tricode)
    except Exception as exc:
        logging.error("Error fetching NBA standings for %s: %s", team_tricode, exc)
    fallback = _fetch_nba_team_standings_espn()
    if fallback:
        return fallback
    logging.warning("Using placeholder NBA standings for %s due to fetch errors", team_tricode)
    return _empty_standings_record(team_tricode)


def fetch_bulls_standings():
    return _fetch_nba_team_standings(NBA_TEAM_TRICODE)


def _fetch_nba_team_standings_espn() -> Optional[dict]:
    """Fallback for NBA standings using ESPN when NBA CDN blocks access."""

    def _iter_entries(node):
        if not isinstance(node, dict):
            return
        standings = node.get("standings", {})
        for entry in standings.get("entries", []) or []:
            yield entry
        for child in node.get("children", []) or []:
            yield from _iter_entries(child)

    def _stat(stats, name, default=None):
        for stat in stats or []:
            if stat.get("name") == name:
                if stat.get("value") is not None:
                    return stat.get("value")
                return stat.get("displayValue") or stat.get("summary")
        return default

    try:
        url = "https://site.web.api.espn.com/apis/v2/sports/basketball/nba/standings"
        resp = _session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json() or {}

        for entry in _iter_entries(data):
            team = entry.get("team", {}) or {}
            if (team.get("abbreviation") or team.get("shortDisplayName")) != NBA_TEAM_TRICODE:
                continue

            stats = entry.get("stats") or []
            streak_code = _stat(stats, "streak", "-")
            pct = _stat(stats, "winPercent")
            try:
                pct = float(pct)
            except Exception:
                pass

            logging.info("Using ESPN NBA standings fallback for %s", NBA_TEAM_TRICODE)
            return {
                "leagueRecord": {
                    "wins": _safe_int(_stat(stats, "wins")),
                    "losses": _safe_int(_stat(stats, "losses")),
                    "pct": pct,
                },
                "divisionRank": _stat(stats, "divisionWinPercent")
                or _stat(stats, "playoffSeed"),
                "divisionGamesBack": _stat(stats, "divisionGamesBehind"),
                "wildCardGamesBack": None,
                "streak": {"streakCode": streak_code or "-"},
                "records": {"splitRecords": []},
            }
    except Exception as exc:
        logging.error("Error fetching NBA standings (ESPN fallback) for %s: %s", NBA_TEAM_TRICODE, exc)
    return None


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------
def _safe_pct(wins, losses, ties=0):
    try:
        games = float(wins) + float(losses) + float(ties)
        return round(float(wins) / games, 3) if games else 0.0
    except Exception:
        return 0.0
