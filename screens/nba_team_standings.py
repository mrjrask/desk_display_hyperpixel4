"""NBA team standings screens."""
from config import FONT_STAND1_RANK_COMPACT, IS_SQUARE_DISPLAY
from screens.mlb_team_standings import (
    draw_standings_screen1 as _base_screen1,
    draw_standings_screen2 as _base_screen2,
)
from utils import log_call


def _preferred_rank(*ranks: object) -> object | None:
    """Return the first positive, non-zero rank value."""
    for rank in ranks:
        try:
            rank_int = int(rank)
        except Exception:
            rank_int = None

        if rank_int is not None:
            if rank_int > 0:
                return rank_int
            continue

        if rank not in (None, ""):
            return rank

    return None


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
    rank_font = FONT_STAND1_RANK_COMPACT if IS_SQUARE_DISPLAY else None
    conference_info = rec.get("conference") or {}
    conference_label = conference_info.get("name") or conference_info.get("abbreviation")
    division_label = (
        conference_label
        or division_name
        or rec.get("division", {}).get("name")
        or "Conference"
    )

    conference_rank = _preferred_rank(
        rec.get("conferenceRank"),
        rec.get("playoffRank"),
    )
    division_rank = conference_rank if conference_rank not in (0, "0", None) else None
    if division_rank is None:
        division_rank = _preferred_rank(rec.get("divisionRank"))
    if division_rank in (0, "0", None):
        division_rank = "-"

    rec_for_display = {
        **rec,
        "divisionRank": division_rank,
    }
    return _base_screen1(
        display,
        rec_for_display,
        logo_path,
        division_label,
        conference_label=conference_label,
        place_gb_before_rank=True,
        show_pct=True,
        show_games_back=False,
        pct_precision=3,
        show_streak=True,
        gb_label=None,
        wild_card_label=None,
        rank_font=rank_font,
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
