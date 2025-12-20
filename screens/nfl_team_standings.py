"""NFL team standings screens."""
from config import FONT_NFL_STAND1_RECORD, FONT_STAND1_RANK_COMPACT, IS_SQUARE_DISPLAY
from screens.mlb_team_standings import (
    draw_standings_screen1 as _base_screen1,
    draw_standings_screen2 as _base_screen2,
)
from utils import log_call


@log_call
def draw_nfl_standings_screen1(display, rec, logo_path, division_name, *, transition=False):
    """Wrap the generic standings screen for NFL teams (no GB/WC columns)."""
    rank_font = FONT_STAND1_RANK_COMPACT if IS_SQUARE_DISPLAY else None
    return _base_screen1(
        display,
        rec,
        logo_path,
        division_name,
        rank_font=rank_font,
        wl_font=FONT_NFL_STAND1_RECORD,
        show_games_back=False,
        show_wild_card=False,
        transition=transition,
    )


@log_call
def draw_nfl_standings_screen2(display, rec, logo_path, *, transition=False):
    """Customize standings screen 2 for NFL teams."""

    return _base_screen2(
        display,
        rec,
        logo_path,
        pct_precision=3,
        split_order=("home", "away", "division", "conference"),
        show_streak=True,
        show_points=True,
        transition=transition,
    )


@log_call
def draw_standings_screen1(display, rec, logo_path, division_name, *, transition=False):
    """Backward-compatible alias for draw_nfl_standings_screen1."""

    return draw_nfl_standings_screen1(
        display,
        rec,
        logo_path,
        division_name,
        transition=transition,
    )


@log_call
def draw_standings_screen2(display, rec, logo_path, *, transition=False):
    """Backward-compatible alias for draw_nfl_standings_screen2."""

    return draw_nfl_standings_screen2(
        display,
        rec,
        logo_path,
        transition=transition,
    )


__all__ = [
    "draw_nfl_standings_screen1",
    "draw_nfl_standings_screen2",
    "draw_standings_screen1",
    "draw_standings_screen2",
]
