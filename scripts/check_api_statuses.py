"""Check availability of external APIs used by the desk display.

The script mirrors the helper maintained in the upstream scripts repository
and is intended to be run from any working directory. It automatically loads
environment variables from the project root `.env` file so configured API keys
are honoured when making test requests.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

# Ensure any locally configured secrets are available for the checks below.
load_dotenv(ENV_PATH)

DEFAULT_LATITUDE = float(os.environ.get("LATITUDE", "41.9103"))
DEFAULT_LONGITUDE = float(os.environ.get("LONGITUDE", "-87.6340"))
DEFAULT_TRAVEL_ORIGIN = os.environ.get(
    "TRAVEL_TO_HOME_ORIGIN", os.environ.get("TRAVEL_TO_WORK_ORIGIN", "Chicago,IL")
)
DEFAULT_TRAVEL_DESTINATION = os.environ.get(
    "TRAVEL_TO_HOME_DESTINATION",
    os.environ.get("TRAVEL_TO_WORK_DESTINATION", "O'Hare International Airport,IL"),
)


@dataclass
class ApiResult:
    name: str
    url: str
    status: str
    http_status: Optional[int]
    detail: str


def _first_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def build_checks() -> List[Dict[str, object]]:
    """Build the list of API checks with any dynamic values resolved."""

    owm_key = _first_env("OWM_API_KEY_VERANO", "OWM_API_KEY_WIFFY", "OWM_API_KEY_DEFAULT", "OWM_API_KEY")
    google_maps_key = os.environ.get("GOOGLE_MAPS_API_KEY")

    checks: List[Dict[str, object]] = [
        {
            "name": "Open-Meteo forecast",
            "url": "https://api.open-meteo.com/v1/forecast",
            "params": {
                "latitude": DEFAULT_LATITUDE,
                "longitude": DEFAULT_LONGITUDE,
                "current_weather": True,
            },
        },
        {
            "name": "ESPN NFL scoreboard",
            "url": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        },
        {
            "name": "ESPN NBA scoreboard",
            "url": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
        },
        {
            "name": "MLB standings",
            "url": "https://statsapi.mlb.com/api/v1/standings",
        },
        {
            "name": "MLB schedule",
            "url": "https://statsapi.mlb.com/api/v1/schedule",
        },
    ]

    if owm_key:
        checks.append(
            {
                "name": "OpenWeatherMap current weather",
                "url": "https://api.openweathermap.org/data/2.5/weather",
                "params": {
                    "lat": DEFAULT_LATITUDE,
                    "lon": DEFAULT_LONGITUDE,
                    "appid": owm_key,
                    "units": "imperial",
                },
            }
        )
    else:
        checks.append(
            {
                "name": "OpenWeatherMap current weather",
                "url": "https://api.openweathermap.org/data/2.5/weather",
                "skip": "OWM_API_KEY not configured",
            }
        )

    if google_maps_key:
        checks.append(
            {
                "name": "Google Maps Directions",
                "url": "https://maps.googleapis.com/maps/api/directions/json",
                "params": {
                    "origin": DEFAULT_TRAVEL_ORIGIN,
                    "destination": DEFAULT_TRAVEL_DESTINATION,
                    "mode": os.environ.get("TRAVEL_MODE", "driving"),
                    "key": google_maps_key,
                },
            }
        )
    else:
        checks.append(
            {
                "name": "Google Maps Directions",
                "url": "https://maps.googleapis.com/maps/api/directions/json",
                "skip": "GOOGLE_MAPS_API_KEY not configured",
            }
        )

    return checks


def check_endpoint(name: str, url: str, *, params: Optional[Dict[str, object]] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> ApiResult:
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        status = "ok" if response.ok else "error"
        detail = f"HTTP {response.status_code}"
        if not response.ok:
            detail = f"{detail}: {response.text[:200]}"
        return ApiResult(name, response.url, status, response.status_code, detail)
    except Exception as exc:  # pragma: no cover - network/runtime errors
        return ApiResult(name, url, "error", None, str(exc))


def format_results(results: Iterable[ApiResult]) -> str:
    lines = []
    for result in results:
        prefix = "✅" if result.status == "ok" else "❌"
        status_bits = [prefix, result.name, result.detail]
        lines.append(" - ".join(status_bits))
        lines.append(f"    URL: {result.url}")
    return "\n".join(lines)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check connectivity to external APIs used by the desk display")
    parser.add_argument("--json", action="store_true", help="Return machine-readable output")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout in seconds (default: 10)")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    results: List[ApiResult] = []
    for check in build_checks():
        if check.get("skip"):
            results.append(
                ApiResult(
                    name=check["name"],
                    url=str(check["url"]),
                    status="skipped",
                    http_status=None,
                    detail=str(check["skip"]),
                )
            )
            continue
        results.append(
            check_endpoint(
                check["name"],
                str(check["url"]),
                params=check.get("params"),
                headers=check.get("headers"),
                timeout=args.timeout,
            )
        )

    if args.json:
        serialised = [
            {
                "name": result.name,
                "url": result.url,
                "status": result.status,
                "http_status": result.http_status,
                "detail": result.detail,
            }
            for result in results
        ]
        print(json.dumps(serialised, indent=2))
    else:
        print(format_results(results))

    # Non-zero exit if any check failed.
    return 0 if all(r.status in {"ok", "skipped"} for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
