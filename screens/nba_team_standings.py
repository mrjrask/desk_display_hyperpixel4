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
    division_label = division_name or (rec or {}).get("division", {}).get("name")
    division_label = division_label or "Division"
    return _base_screen1(
        display,
        rec,
        logo_path,
        division_label,
        conference_label=None,
        place_gb_before_rank=True,
        show_pct=True,
        pct_precision=3,
        show_streak=True,
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
