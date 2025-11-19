#!/usr/bin/env python3
"""Stacked-logo layout (v3) for the NHL Scoreboard."""

from __future__ import annotations

from utils import ScreenImage, log_call

from screens import nhl_scoreboard_v2 as base
from screens.scoreboard_v3_layout import ScoreboardV3Adapter, draw_stacked_logo_scoreboard


def _extract_teams(game: dict) -> tuple[dict, dict]:
    teams = (game or {}).get("teams", {}) or {}
    return teams.get("away", {}) or {}, teams.get("home", {}) or {}


def _fetch_games() -> list[dict]:
    return base._fetch_games_for_date(base._scoreboard_date())


_ADAPTER = ScoreboardV3Adapter(
    title="NHL Scoreboard v3",
    base_module=base,
    fetch_games=_fetch_games,
    extract_teams=_extract_teams,
    team_accessor=lambda side: (side or {}).get("team", {}),
)


@log_call
def draw_nhl_scoreboard_v3(display, transition: bool = False) -> ScreenImage:
    return draw_stacked_logo_scoreboard(display, _ADAPTER, transition=transition)

