#!/usr/bin/env python3
"""Stacked-logo layout (v3) for the NFL Scoreboard."""

from __future__ import annotations

from typing import Tuple

from utils import ScreenImage, log_call

from screens import nfl_scoreboard_v2 as base
from screens.scoreboard_v3_layout import ScoreboardV3Adapter, draw_stacked_logo_scoreboard


def _extract_teams(game: dict) -> Tuple[dict, dict]:
    competitors = (game or {}).get("competitors", []) or []
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    return away, home


_ADAPTER = ScoreboardV3Adapter(
    title="NFL Scoreboard v3",
    base_module=base,
    fetch_games=base._fetch_games_for_week,
    extract_teams=_extract_teams,
    team_accessor=lambda side: (side or {}).get("team", {}),
    possession_lookup=getattr(base, "_team_has_possession", None),
)


@log_call
def draw_nfl_scoreboard_v3(display, transition: bool = False) -> ScreenImage:
    return draw_stacked_logo_scoreboard(display, _ADAPTER, transition=transition)

