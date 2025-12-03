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
import socket
import time
from typing import Optional

import pytz
import requests

from services.http_client import NHL_HEADERS, get_session
from screens.nba_scoreboard import _fetch_games_for_date as _nba_fetch_games_for_date

from config import (
    OWM_API_KEY,
    ONE_CALL_URL,
    LATITUDE,
    LONGITUDE,
    NHL_API_URL,
    NHL_TEAM_ID,
    MLB_API_URL,
    MLB_CUBS_TEAM_ID,
    MLB_SOX_TEAM_ID,
    CENTRAL_TIME,
    OPEN_METEO_URL,
    OPEN_METEO_PARAMS,
    NBA_TEAM_ID,
    NBA_TEAM_TRICODE,
)

# ─── Shared HTTP session ─────────────────────────────────────────────────────
_session = get_session()

# Track last time we received a 429 from OWM
_last_owm_429 = None
# Cache statsapi DNS availability to avoid repeated slow lookups
_statsapi_dns_available: Optional[bool] = None
_statsapi_dns_checked_at: Optional[float] = None
_STATSAPI_DNS_RECHECK_SECONDS = 600

# -----------------------------------------------------------------------------
# WEATHER
# -----------------------------------------------------------------------------
def fetch_weather():
    """
    Fetch weather from OpenWeatherMap OneCall, falling back to Open-Meteo on errors
    or if recently rate-limited.
    """
    global _last_owm_429
    now = datetime.datetime.now()
    if not OWM_API_KEY:
        logging.warning("OpenWeatherMap API key missing; using fallback provider")
        return fetch_weather_fallback()
    # If we got a 429 within the last 2 hours, skip OWM and fallback
    if _last_owm_429 and (now - _last_owm_429) < datetime.timedelta(hours=2):
        logging.warning("Skipping OpenWeatherMap due to recent 429; using fallback")
        return fetch_weather_fallback()

    try:
        params = {
            "lat": LATITUDE,
            "lon": LONGITUDE,
            "appid": OWM_API_KEY,
            "units": "imperial",
        }
        r = _session.get(ONE_CALL_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    except requests.exceptions.HTTPError as http_err:
        if r.status_code == 429:
            logging.warning("HTTP 429 from OWM; falling back and pausing OWM for 2h")
            _last_owm_429 = datetime.datetime.now()
            return fetch_weather_fallback()
        logging.error("HTTP error fetching weather: %s", http_err)
        return None

    except Exception as e:
        logging.error("Error fetching weather: %s", e)
        return None


def fetch_weather_fallback():
    """
    Fallback using Open-Meteo API for weather data.
    """
    try:
        r = _session.get(OPEN_METEO_URL, params=OPEN_METEO_PARAMS, timeout=10)
        r.raise_for_status()
        data = r.json()
        logging.debug("Weather data (Open-Meteo): %s", data)

        current = data.get("current_weather", {})
        daily   = data.get("daily", {})

        mapped = {
            "current": {
                "temp":        current.get("temperature"),
                "feels_like":  current.get("temperature"),
                "weather": [{
                    "description": weather_code_to_description(
                        current.get("weathercode", -1)
                    )
                }],
                "wind_speed":  current.get("windspeed"),
                "wind_deg":    current.get("winddirection"),
                "humidity":    (daily.get("relativehumidity_2m") or [0])[0],
                "pressure":    (daily.get("surface_pressure")   or [0])[0],
                "uvi":         0,
                "sunrise":     (daily.get("sunrise")  or [None])[0],
                "sunset":      (daily.get("sunset")   or [None])[0],
            },
            "daily": [{
                "temp": {
                    "max": (daily.get("temperature_2m_max") or [None])[0],
                    "min": (daily.get("temperature_2m_min") or [None])[0],
                },
                "sunrise": (daily.get("sunrise") or [None])[0],
                "sunset":  (daily.get("sunset")  or [None])[0],
            }],
        }
        return mapped

    except Exception as e:
        logging.error("Error fetching fallback weather: %s", e)
        return None


def weather_code_to_description(code):
    mapping = {
        0:  "Clear sky",     1: "Mainly clear",  2: "Partly cloudy", 3: "Overcast",
        45: "Fog",           48: "Rime fog",     51: "Light drizzle", 53: "Mod. drizzle",
        55: "Dense drizzle", 61: "Slight rain",  63: "Mod. rain",     65: "Heavy rain",
        80: "Rain showers",  81: "Mod. showers", 82: "Violent showers",
        95: "Thunderstorm",  96: "Thunder w/ hail", 99: "Thunder w/ hail"
    }
    return mapping.get(code, f"Code {code}")


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
_NBA_LOOKAHEAD_DAYS = 14


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
        for game in _future_bulls_games(_NBA_LOOKAHEAD_DAYS):
            teams = game.get("teams") or {}
            if _is_bulls_team(teams.get("home")) and _nba_game_state(game) in {"preview", "scheduled", "pregame"}:
                return game
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
    def _load_json() -> Optional[dict]:
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
                return data
            except Exception as exc:
                logging.error("Error fetching NBA standings from %s: %s", base, exc)
        return _fetch_nba_team_standings_espn()

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

            splits = _extract_split_records(
                lastTen=entry.get("lastTen"),
                home=entry.get("home"),
                away=entry.get("away"),
            )

            return {
                "leagueRecord": record,
                "divisionRank": entry.get("divisionRank")
                or (entry.get("teamDivision") or {}).get("rank"),
                "divisionGamesBack": entry.get("gamesBehind")
                or entry.get("gamesBehindDivision"),
                "wildCardGamesBack": None,
                "streak": {"streakCode": streak_code},
                "records": {"splitRecords": splits},
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
