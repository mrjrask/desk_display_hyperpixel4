"""NHL team standings screens."""
from config import FONT_STAND1_RANK_COMPACT, IS_SQUARE_DISPLAY
from screens.mlb_team_standings import (
    draw_standings_screen1 as _base_screen1,
    draw_standings_screen2 as _base_screen2,
    _format_int,
)
from utils import log_call


@log_call
def draw_nhl_standings_screen1(
    display,
    rec,
    logo_path,
    division_name: str | None = None,
    *,
    transition=False,
):
    """Wrap the generic standings screen for NHL teams (no GB/WC columns)."""
    rec = rec or {}
    conference_name = (rec.get("conference") or {}).get("name")
    conference_name = conference_name or rec.get("conferenceName")
    conference_name = conference_name or division_name or "Conference"
    rank_font = FONT_STAND1_RANK_COMPACT if IS_SQUARE_DISPLAY else None

    def _record_line(record_obj, base_rec):
        record_data = record_obj.get("leagueRecord", {}) if isinstance(record_obj, dict) else {}
        wins = _format_int(record_data.get("wins"))
        losses = _format_int(record_data.get("losses"))
        ot = _format_int(record_data.get("ot"))
        if ot != "-":
            return f"{wins}-{losses}-{ot}"
        return f"{wins}-{losses}"

    rec_for_display = {
        **rec,
        "divisionRank": rec.get("conferenceRank"),
        "divisionGamesBack": None,
        "division": {"name": conference_name},
    }

    return _base_screen1(
        display,
        rec_for_display,
        logo_path,
        conference_name,
        show_games_back=False,
        show_wild_card=False,
        ot_label=None,
        points_label="points",
        conference_label=None,
        show_conference_rank=False,
        record_details_fn=_record_line,
        last_place_rank=None,
        transition=transition,
    )


def _nhl_record_details(rec, base_rec):
    pts_val = _format_int(rec.get("points"))
    return f"{base_rec} ({pts_val} pts)"


@log_call
def draw_nhl_standings_screen2(display, rec, logo_path, *, transition=False):
    """Customize standings screen 2 for NHL teams."""

    return _base_screen2(
        display,
        rec,
        logo_path,
        record_details_fn=_nhl_record_details,
        split_order=("division", "conference", "home", "away"),
        show_streak=False,
        show_points=False,
        transition=transition,
    )


__all__ = ["draw_nhl_standings_screen1", "draw_nhl_standings_screen2"]
