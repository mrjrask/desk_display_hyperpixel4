"""NBA team standings screens."""
from config import FONT_STAND1_RANK_COMPACT, IS_SQUARE_DISPLAY
from screens.mlb_team_standings import (
    draw_standings_screen1 as _base_screen1,
    draw_standings_screen2 as _base_screen2,
)
from utils import log_call


def _normalize_rank(value):
    """Return a positive integer rank or ``None`` when not available.

    NBA feeds occasionally surface placeholders (``0``, ``0.0``, ``None``)
    when rank details are unavailable. Returning ``None`` ensures the screen
    renders "-" instead of an incorrect "0th" label.
    """

    if value in (None, "", "-"):
        return None

    try:
        number = float(value)
    except Exception:
        return value

    if not number.is_integer():
        return None

    number = int(number)
    return number if number > 0 else None


def _strip_pct_leading_zero(rec, *, precision=3):
    """Return a copy of the record with pct formatted without a leading zero."""

    if not rec:
        return rec

    league_record = rec.get("leagueRecord")
    if not isinstance(league_record, dict):
        return rec

    pct_val = league_record.get("pct")
    if pct_val in (None, ""):
        return rec

    try:
        pct_txt = f"{float(pct_val):.{precision}f}".lstrip("0")
    except Exception:
        pct_txt = str(pct_val).lstrip("0")

    updated_record = {**league_record, "pct": pct_txt}
    return {**rec, "leagueRecord": updated_record}


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

    rec_clean = _strip_pct_leading_zero(rec)
    conference_info = rec_clean.get("conference") if isinstance(rec_clean, dict) else {}
    conference_label = None
    if isinstance(conference_info, dict):
        conference_label = conference_info.get("name") or conference_info.get("abbreviation")

    conference_label = (
        conference_label
        or (rec_clean or {}).get("conferenceName")
        or (rec_clean or {}).get("conferenceAbbrev")
        or "conference"
    )
    division_label = (
        division_name
        or (rec_clean or {}).get("division", {}).get("name")
        or (rec_clean or {}).get("divisionName")
        or (rec_clean or {}).get("divisionAbbrev")
        or "division"
    )

    conference_rank = None
    division_rank = None
    if isinstance(rec_clean, dict):
        conference_rank = (
            rec_clean.get("conferenceRank")
            or rec_clean.get("playoffRank")
            or rec_clean.get("divisionRank")
        )
        division_rank = rec_clean.get("divisionRank")

    conference_rank = _normalize_rank(conference_rank) or "-"
    division_rank = _normalize_rank(division_rank) or "-"

    rank_font = FONT_STAND1_RANK_COMPACT if IS_SQUARE_DISPLAY else None

    rec_for_display = {
        **(rec_clean or {}),
        "divisionRank": division_rank,
        "conferenceRank": conference_rank,
        "conferenceName": conference_label,
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
        _strip_pct_leading_zero(rec),
        logo_path,
        pct_precision=3,
        transition=transition,
    )


__all__ = ["draw_nba_standings_screen1", "draw_nba_standings_screen2"]
