#!/usr/bin/env python3
"""Stacked-logo layout (v3) for the MLB Scoreboard."""

from __future__ import annotations

import datetime

from config import CENTRAL_TIME
from utils import ScreenImage, log_call

from screens import mlb_scoreboard_v2 as base
from screens.scoreboard_v3_layout import ScoreboardV3Adapter, draw_stacked_logo_scoreboard


def _extract_teams(game: dict) -> tuple[dict, dict]:
    teams = (game or {}).get("teams", {}) or {}
    return teams.get("away", {}) or {}, teams.get("home", {}) or {}


def _fetch_games() -> list[dict]:
    now = datetime.datetime.now(CENTRAL_TIME)
    target_date = base._scoreboard_date(now)
    games = base._fetch_games_for_date(target_date)

    if not games:
        today = now.date()
        if today != target_date:
            today_games = base._fetch_games_for_date(today)
            if today_games:
                games = today_games

    return games


_ADAPTER = ScoreboardV3Adapter(
    title="MLB Scoreboard v3",
    base_module=base,
    fetch_games=_fetch_games,
    extract_teams=_extract_teams,
    team_accessor=lambda side: (side or {}).get("team", {}),
)


@log_call
def draw_mlb_scoreboard_v3(display, transition: bool = False) -> ScreenImage:
    return draw_stacked_logo_scoreboard(display, _ADAPTER, transition=transition)

