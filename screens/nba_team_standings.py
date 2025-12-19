"""NBA team standings screens."""
from screens.mlb_team_standings import (
    draw_standings_screen1 as _base_screen1,
    draw_standings_screen2 as _base_screen2,
)
from utils import log_call


@log_call
def draw_nba_standings_screen1(
    display,
    rec,
    logo_path,
    division_name: str | None = None,
    *,
    transition=False,
):
    """Wrap the generic standings screen for NBA teams (shows games back)."""
    rec = rec or {}
    division_label = division_name or rec.get("division", {}).get("name")
    division_label = division_label or "Division"
    rec_for_display = {
        **rec,
        "divisionRank": rec.get("divisionRank") or rec.get("conferenceRank"),
    }
    return _base_screen1(
        display,
        rec_for_display,
        logo_path,
        division_label,
        conference_label=None,
        place_gb_before_rank=True,
        show_pct=True,
        show_games_back=False,
        pct_precision=3,
        show_streak=True,
        gb_label=None,
        wild_card_label=None,
        transition=transition,
    )


@log_call
def draw_nba_standings_screen2(display, rec, logo_path, *, transition=False):
    """Customize standings screen 2 for NBA teams."""

    return _base_screen2(
        display,
        rec,
        logo_path,
        pct_precision=3,
        transition=transition,
    )


__all__ = ["draw_nba_standings_screen1", "draw_nba_standings_screen2"]
