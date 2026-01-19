#!/usr/bin/env python3
"""
nfl_scoreboard_v2.py

Dual-game layout version of NFL Scoreboard - shows 2 games per row.
Maintains the same data fetching as the original but with a creative
side-by-side layout to maximize screen usage.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import time
from typing import Iterable, Optional

import requests
from PIL import Image, ImageDraw

try:
    RESAMPLE = Image.ANTIALIAS
except AttributeError:  # Pillow ≥11
    RESAMPLE = Image.Resampling.LANCZOS

from config import (
    WIDTH,
    HEIGHT,
    IS_SQUARE_DISPLAY,
    FONT_TITLE_SPORTS,
    FONT_TEAM_SPORTS,
    FONT_STATUS,
    FONT_EMOJI,
    CENTRAL_TIME,
    IMAGES_DIR,
    SCOREBOARD_LOGO_HEIGHT_COMPACT,
    SCOREBOARD_SCROLL_STEP,
    SCOREBOARD_SCROLL_DELAY,
    SCOREBOARD_SCROLL_PAUSE_TOP,
    SCOREBOARD_SCROLL_PAUSE_BOTTOM,
    SCOREBOARD_BACKGROUND_COLOR,
    SCOREBOARD_IN_PROGRESS_SCORE_COLOR,
    SCOREBOARD_FINAL_WINNING_SCORE_COLOR,
    SCOREBOARD_FINAL_LOSING_SCORE_COLOR,
)
from utils import (
    ScreenImage,
    clear_display,
    clone_font,
    load_team_logo,
    log_call,
)

# ─── Constants ────────────────────────────────────────────────────────────────
TITLE               = "NFL Scoreboard"
TITLE_GAP           = 12
BLOCK_SPACING       = 15
SCORE_ROW_H         = 150
STATUS_ROW_H        = 48
REQUEST_TIMEOUT     = 10

# Dual-game layout: 2 games per row
GAMES_PER_ROW = 2
GAME_WIDTH = WIDTH // 2  # 360px per game
GAME_HEIGHT = SCORE_ROW_H + STATUS_ROW_H

# Adjusted column widths for narrower game area (total should be < 360)
COL_WIDTHS = [55, 85, 50, 85, 55]  # total = 330 (fits in 360)
_TOTAL_COL_WIDTH = sum(COL_WIDTHS)
_COL_LEFT = (GAME_WIDTH - _TOTAL_COL_WIDTH) // 2

_SCORE_PT = 75 - (4 if IS_SQUARE_DISPLAY else 0) - 5
_STATUS_PT = 42 - (4 if IS_SQUARE_DISPLAY else 0)
_CENTER_PT = 54 - (4 if IS_SQUARE_DISPLAY else 0)

SCORE_FONT              = clone_font(FONT_TEAM_SPORTS, _SCORE_PT)
STATUS_FONT             = clone_font(FONT_STATUS, max(8, _STATUS_PT))
CENTER_FONT             = clone_font(FONT_STATUS, max(8, _CENTER_PT))
TITLE_FONT              = FONT_TITLE_SPORTS
LOGO_HEIGHT             = max(1, int(round(SCOREBOARD_LOGO_HEIGHT_COMPACT * 0.7)))
LOGO_GAP_MARGIN         = 6
LOGO_DIR                = os.path.join(IMAGES_DIR, "nfl")
LEAGUE_LOGO_KEYS        = ("NFL", "nfl")
LEAGUE_LOGO_GAP         = 10
LEAGUE_LOGO_HEIGHT      = LOGO_HEIGHT
LEAGUE_LOGO_MAX_WIDTH   = COL_WIDTHS[1] - LOGO_GAP_MARGIN
SUPER_BOWL_LOGO_NAME    = "SB"
SUPER_BOWL_LOGO_GAP     = 16
SUPER_BOWL_LOGO_MAX_WIDTH = WIDTH - 180
SUPER_BOWL_LOGO_MAX_HEIGHT = 120
IN_PROGRESS_SCORE_COLOR = SCOREBOARD_IN_PROGRESS_SCORE_COLOR
IN_PROGRESS_STATUS_COLOR = IN_PROGRESS_SCORE_COLOR
FINAL_WINNING_SCORE_COLOR = SCOREBOARD_FINAL_WINNING_SCORE_COLOR
FINAL_LOSING_SCORE_COLOR = SCOREBOARD_FINAL_LOSING_SCORE_COLOR
BACKGROUND_COLOR = SCOREBOARD_BACKGROUND_COLOR
STATUS_TEXT_NUDGE = -12

_POSSESSION_IDENTIFIER_KEYS = ("id", "abbreviation", "abbrev", "slug")

IN_GAME_STATUS_OVERRIDES = {
    "end of the 1st": "End of the 1st",
    "end of 1st": "End of the 1st",
    "halftime": "Halftime",
    "end of the 3rd": "End of the 3rd",
    "end of 3rd": "End of the 3rd",
}

_LOGO_CACHE: dict[str, Optional[Image.Image]] = {}
_LEAGUE_LOGO: Optional[Image.Image] = None
_LEAGUE_LOGO_LOADED = False
_POSSESSION_ICON: Optional[Image.Image] = None
_POSSESSION_FONT_SIZE = max(18, LOGO_HEIGHT // 3)
_SUPER_BOWL_LOGO: Optional[Image.Image] = None
_SUPER_BOWL_LOGO_LOADED = False


# ─── Helpers (reused from original) ──────────────────────────────────────────
def _in_playoff_window(now: datetime.datetime) -> bool:
    return now.month in (1, 2)


def _playoff_cutoff(week_start: datetime.date, game_count: int) -> Optional[datetime.datetime]:
    if game_count == 6:
        cutoff_date = week_start + datetime.timedelta(days=5)
        cutoff_time = datetime.time(hour=15, minute=0)
    elif game_count in (2, 4):
        cutoff_date = week_start + datetime.timedelta(days=4)
        cutoff_time = datetime.time(hour=15, minute=15)
    else:
        return None
    return CENTRAL_TIME.localize(datetime.datetime.combine(cutoff_date, cutoff_time))


def _should_advance_playoff_week(
    now: datetime.datetime, week_start: datetime.date, game_count: int
) -> bool:
    if not _in_playoff_window(now):
        return False
    cutoff = _playoff_cutoff(week_start, game_count)
    if cutoff is None:
        return False
    return now >= cutoff


def _week_start(now: Optional[datetime.datetime] = None) -> datetime.date:
    now = now or datetime.datetime.now(CENTRAL_TIME)

    if now.weekday() == 2:  # Wednesday
        cutoff = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= cutoff:
            ref_date = now.date() + datetime.timedelta(days=1)
        else:
            ref_date = now.date()
    else:
        ref_date = now.date()

    days_since_thursday = (ref_date.weekday() - 3) % 7
    return ref_date - datetime.timedelta(days=days_since_thursday)


def _week_dates(now: Optional[datetime.datetime] = None) -> list[datetime.date]:
    start = _week_start(now)
    return [start + datetime.timedelta(days=offset) for offset in range(5)]


def _load_logo_cached(abbr: str) -> Optional[Image.Image]:
    key = (abbr or "").strip()
    if not key:
        return None
    cache_key = key.upper()
    if cache_key in _LOGO_CACHE:
        return _LOGO_CACHE[cache_key]

    candidates = [cache_key, cache_key.lower(), cache_key.title()]
    for candidate in candidates:
        path = os.path.join(LOGO_DIR, f"{candidate}.png")
        if os.path.exists(path):
            logo = load_team_logo(LOGO_DIR, candidate, height=LOGO_HEIGHT)
            _LOGO_CACHE[cache_key] = logo
            return logo

    _LOGO_CACHE[cache_key] = None
    return None


def _get_league_logo() -> Optional[Image.Image]:
    global _LEAGUE_LOGO, _LEAGUE_LOGO_LOADED
    if not _LEAGUE_LOGO_LOADED:
        for key in LEAGUE_LOGO_KEYS:
            logo = load_team_logo(LOGO_DIR, key, height=LEAGUE_LOGO_HEIGHT)
            if logo is not None:
                _LEAGUE_LOGO = _fit_logo_to_width(logo, LEAGUE_LOGO_MAX_WIDTH)
                break
        _LEAGUE_LOGO_LOADED = True
    return _LEAGUE_LOGO


def _fit_logo_to_bounds(
    logo: Image.Image, max_width: int, max_height: int
) -> Optional[Image.Image]:
    if logo is None or max_width <= 0 or max_height <= 0:
        return None
    scale = min(max_width / logo.width, max_height / logo.height, 1.0)
    if scale >= 1.0:
        return logo
    new_width = max(1, int(round(logo.width * scale)))
    new_height = max(1, int(round(logo.height * scale)))
    return logo.resize((new_width, new_height), resample=RESAMPLE)


def _get_super_bowl_logo() -> Optional[Image.Image]:
    global _SUPER_BOWL_LOGO, _SUPER_BOWL_LOGO_LOADED
    if not _SUPER_BOWL_LOGO_LOADED:
        path = os.path.join(LOGO_DIR, f"{SUPER_BOWL_LOGO_NAME}.png")
        try:
            _SUPER_BOWL_LOGO = Image.open(path).convert("RGBA")
        except Exception as exc:
            logging.warning("Could not load Super Bowl logo '%s': %s", path, exc)
            _SUPER_BOWL_LOGO = None
        _SUPER_BOWL_LOGO_LOADED = True
    if _SUPER_BOWL_LOGO is None:
        return None
    return _fit_logo_to_bounds(_SUPER_BOWL_LOGO, SUPER_BOWL_LOGO_MAX_WIDTH, SUPER_BOWL_LOGO_MAX_HEIGHT)


def _get_possession_icon() -> Optional[Image.Image]:
    global _POSSESSION_ICON
    if _POSSESSION_ICON is not None:
        return _POSSESSION_ICON

    try:
        base_size = max(18, LOGO_HEIGHT // 4)
        # Use the emoji font instead of the status font to properly display the football emoji
        font = clone_font(FONT_EMOJI, max(base_size, _POSSESSION_FONT_SIZE))
        glyph = "🏈"

        # Measure the emoji in a generous temporary canvas to preserve its
        # aspect ratio before cropping down to the rendered bounds.
        temp_size = max(32, int(base_size * 2.4))
        temp = Image.new("RGBA", (temp_size, temp_size), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp)
        try:
            left, top, right, bottom = temp_draw.textbbox((0, 0), glyph, font=font)
        except Exception:
            width, height = temp_draw.textsize(glyph, font=font)
            left, top, right, bottom = 0, 0, width, height

        width = max(1, right - left)
        height = max(1, bottom - top)
        icon = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(icon)
        draw.text((-left, -top), glyph, font=font, embedded_color=True)

        _POSSESSION_ICON = icon
        return _POSSESSION_ICON
    except Exception:
        _POSSESSION_ICON = None
        return None


def _team_logo_abbr(team: dict) -> str:
    if not isinstance(team, dict):
        return ""
    for key in ("abbreviation", "abbrev", "shortDisplayName", "displayName"):
        value = team.get(key)
        if isinstance(value, str) and value.strip():
            candidate = value.strip().upper()
            for suffix in (candidate, candidate.lower()):
                if os.path.exists(os.path.join(LOGO_DIR, f"{suffix}.png")):
                    return candidate
    nickname = (team.get("nickname") or team.get("name") or "").strip()
    return nickname[:3].upper() if nickname else ""


def _should_display_scores(game: dict) -> bool:
    status = (game or {}).get("status", {}) or {}
    type_info = status.get("type") or {}
    state = (type_info.get("state") or "").lower()
    if state in {"in", "post"}:
        return True
    if (type_info.get("completed") or False) is True:
        return True
    return False


def _is_game_in_progress(game: dict) -> bool:
    status = (game or {}).get("status", {}) or {}
    type_info = status.get("type") or {}
    state = (type_info.get("state") or "").lower()
    return state == "in"


def _is_game_final(game: dict) -> bool:
    status = (game or {}).get("status", {}) or {}
    type_info = status.get("type") or {}
    state = (type_info.get("state") or "").lower()
    completed = type_info.get("completed")
    if state == "post":
        return True
    if isinstance(completed, bool) and completed:
        return True
    description = (type_info.get("description") or "").lower()
    if "final" in description:
        return True
    return False


def _score_text(side: dict, *, show: bool) -> str:
    if not show:
        return _record_text(side)
    score = (side or {}).get("score")
    return "—" if score is None else str(score)


def _score_value(side: dict) -> Optional[int]:
    score = (side or {}).get("score")
    if isinstance(score, (int, float)):
        return int(score)
    if isinstance(score, str):
        cleaned = score.strip()
        if cleaned.isdigit():
            try:
                return int(cleaned)
            except Exception:
                return None
        try:
            return int(float(cleaned))
        except Exception:
            return None
    return None


def _normalize_record_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if re.match(r"^-?\d+(?:\.\d+)?$", text):
                return int(float(text))
    except Exception:
        return None
    return None


def _record_from_summary(text: str) -> Optional[tuple[int, int, Optional[int]]]:
    if not isinstance(text, str) or not text.strip():
        return None
    numbers = [int(part) for part in re.findall(r"\d+", text)]
    if len(numbers) < 2:
        return None
    wins, losses = numbers[0], numbers[1]
    tie = numbers[2] if len(numbers) > 2 else None
    return wins, losses, tie


def _record_from_data(data: object) -> Optional[tuple[int, int, Optional[int]]]:
    if isinstance(data, dict):
        wins = _normalize_record_int(data.get("wins") or data.get("win"))
        losses = _normalize_record_int(data.get("losses") or data.get("loss"))
        ties = _normalize_record_int(
            data.get("ties")
            or data.get("tie")
            or data.get("draws")
            or data.get("ot")
            or data.get("overtime")
        )
        if wins is not None and losses is not None:
            return wins, losses, ties

        for key in ("displayValue", "summary", "text", "overall"):
            summary = data.get(key)
            record = _record_from_summary(summary)
            if record:
                return record
    elif isinstance(data, str):
        return _record_from_summary(data)
    return None


def _team_record(side: dict) -> Optional[tuple[int, int, Optional[int]]]:
    if not isinstance(side, dict):
        return None

    records = side.get("records")
    if isinstance(records, list):
        for record in records:
            parsed = _record_from_data(record)
            if parsed:
                return parsed

    for key in ("record", "overallRecord", "teamRecord", "leagueRecord", "seriesRecord"):
        parsed = _record_from_data(side.get(key))
        if parsed:
            return parsed

    team = side.get("team")
    if isinstance(team, dict):
        for key in ("record", "overallRecord", "teamRecord", "leagueRecord"):
            parsed = _record_from_data(team.get(key))
            if parsed:
                return parsed

    return None


def _record_text(side: dict) -> str:
    record = _team_record(side)
    if not record:
        return "—"
    wins, losses, ties = record
    if wins is None or losses is None:
        return "—"
    if ties:
        return f"({wins}-{losses}-{ties})"
    return f"({wins}-{losses})"


def _team_identifier_tokens(team: dict) -> list[str]:
    if not isinstance(team, dict):
        return []

    tokens: list[str] = []
    seen: set[str] = set()

    def _add(token: str) -> None:
        if token and token not in seen:
            tokens.append(token)
            seen.add(token)

    for key in _POSSESSION_IDENTIFIER_KEYS:
        if key not in team:
            continue
        value = team.get(key)
        if value is None:
            continue

        if isinstance(value, (int, float)):
            if key != "id":
                continue
            text = str(int(value))
        else:
            text = str(value).strip()

        if not text:
            continue

        if key == "id":
            _add(text)
            continue

        normalized = text.lower()
        _add(normalized)

        for part in re.split(r"[^0-9A-Za-z]+", normalized):
            if part:
                _add(part)

    return tokens


def _team_result(side: dict, opponent: dict) -> Optional[str]:
    for key in ("isWinner", "winner", "won"):
        value = (side or {}).get(key)
        if isinstance(value, bool):
            return "win" if value else "loss"

    side_score = _score_value(side)
    opp_score = _score_value(opponent)
    if side_score is not None and opp_score is not None:
        if side_score > opp_score:
            return "win"
        if side_score < opp_score:
            return "loss"
    return None


def _final_results(away: dict, home: dict) -> dict:
    away_result = _team_result(away, home)
    home_result = _team_result(home, away)

    if away_result == "win":
        home_result = "loss"
    elif away_result == "loss":
        home_result = "win"
    elif home_result == "win":
        away_result = "loss"
    elif home_result == "loss":
        away_result = "win"

    return {"away": away_result, "home": home_result}


def _build_possession_lookup(game: dict) -> dict[str, Optional[str]]:
    lookup: dict[str, Optional[str]] = {}
    ambiguous: set[str] = set()
    competitors = (game or {}).get("competitors", []) or []
    for competitor in competitors:
        side = competitor.get("homeAway")
        if side not in {"away", "home"}:
            continue
        team = competitor.get("team") or {}
        for token in _team_identifier_tokens(team):
            if token in ambiguous:
                continue
            if token not in lookup:
                lookup[token] = side
                continue
            existing = lookup[token]
            if existing is None:
                continue
            if existing != side:
                lookup[token] = None
                ambiguous.add(token)
                continue
            lookup[token] = side
    return lookup


def _tokenize_possession_text(text: str) -> list[str]:
    if not text:
        return []
    return [token for token in re.findall(r"[0-9A-Za-z]+", text.lower()) if token]


def _candidate_possession_strings(game: dict) -> list[str]:
    situation = (game or {}).get("situation", {}) or {}
    candidates: list[str] = []

    for key in (
        "possessionText",
        "shortDownDistanceText",
        "downDistanceText",
        "lastPlayText",
    ):
        value = situation.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)

    last_play = situation.get("lastPlay")
    if isinstance(last_play, dict):
        for key in ("text", "shortText"):
            value = last_play.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value)

    return candidates


def _find_possession_side(game: dict) -> Optional[str]:
    competitors = (game or {}).get("competitors", []) or []
    if not competitors:
        return None

    situation = (game or {}).get("situation", {}) or {}
    possession_id = situation.get("possession")
    if possession_id is not None:
        poss_id = str(possession_id).strip()
        if poss_id:
            for competitor in competitors:
                team = competitor.get("team") or {}
                team_id = team.get("id")
                if team_id is None:
                    continue
                if str(team_id).strip() == poss_id:
                    side = competitor.get("homeAway")
                    if side in {"away", "home"}:
                        return side

    lookup = _build_possession_lookup(game)
    if not lookup:
        return None

    last_play = situation.get("lastPlay")
    if isinstance(last_play, dict):
        team_info = last_play.get("team")
        if isinstance(team_info, dict):
            last_play_matches: set[str] = set()
            for token in _team_identifier_tokens(team_info):
                side = lookup.get(token)
                if side:
                    last_play_matches.add(side)
                if len(last_play_matches) > 1:
                    break
            if len(last_play_matches) == 1:
                return next(iter(last_play_matches))

    matched: set[str] = set()
    for text in _candidate_possession_strings(game):
        for token in _tokenize_possession_text(text):
            side = lookup.get(token)
            if not side:
                continue
            matched.add(side)
            if len(matched) > 1:
                return None

    if len(matched) == 1:
        return next(iter(matched))

    return None


def _team_has_possession(game: dict) -> dict[str, bool]:
    side = _find_possession_side(game)
    return {"away": side == "away", "home": side == "home"}


def _score_fill(team_key: str, *, in_progress: bool, final: bool, results: dict) -> tuple[int, int, int]:
    if in_progress:
        return IN_PROGRESS_SCORE_COLOR
    if final:
        result = results.get(team_key)
        if result == "loss":
            return FINAL_LOSING_SCORE_COLOR
        if result == "win":
            return FINAL_WINNING_SCORE_COLOR
    return (255, 255, 255)


def _format_status(game: dict) -> str:
    status = (game or {}).get("status", {}) or {}
    type_info = status.get("type") or {}
    short_detail = (type_info.get("shortDetail") or "").strip()
    detail = (type_info.get("detail") or "").strip()
    state = (type_info.get("state") or "").lower()
    detail_lower = detail.lower()
    short_detail_lower = short_detail.lower()

    if "postponed" in detail_lower or "postponed" in short_detail_lower:
        return "Postponed"

    def _override_in_game_status() -> Optional[str]:
        for candidate in (short_detail, detail):
            normalized = (candidate or "").strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in IN_GAME_STATUS_OVERRIDES:
                return IN_GAME_STATUS_OVERRIDES[key]
        return None

    if state == "post":
        return short_detail or detail or "Final"
    if state == "in":
        override = _override_in_game_status()
        if override:
            return override
        clock = status.get("displayClock") or ""
        period = status.get("period")
        if clock and period:
            return f"{clock} Q{period}"
        return short_detail or detail or "In Progress"

    if state == "pre":
        start_local = game.get("_start_local")
        if isinstance(start_local, datetime.datetime):
            time_text = start_local.strftime("%I:%M %p").lstrip("0")
            if start_local.weekday() != 6:  # Not Sunday
                day_text = start_local.strftime("%a")
                return f"{day_text} {time_text}"
            return time_text
        return short_detail or detail or "TBD"

    return short_detail or detail or "TBD"


def _center_text(draw: ImageDraw.ImageDraw, text: str, font, x: int, width: int,
                 y: int, height: int, *, fill=(255, 255, 255)):
    if not text:
        return
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = r - l, b - t
        tx = x + (width - tw) // 2 - l
        ty = y + (height - th) // 2 - t
    except Exception:
        tw, th = draw.textsize(text, font=font)
        tx = x + (width - tw) // 2
        ty = y + (height - th) // 2
    draw.text((tx, ty), text, font=font, fill=fill)


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    if not text:
        return 0, 0
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l, b - t
    except Exception:
        return draw.textsize(text, font=font)


def _logo_target_width(gap: int, column_width: int) -> int:
    usable_gap = gap - LOGO_GAP_MARGIN
    usable_column = column_width - LOGO_GAP_MARGIN
    return max(0, min(usable_gap, usable_column))


def _fit_logo_to_width(logo: Image.Image, max_width: int) -> Optional[Image.Image]:
    if logo is None or max_width <= 0:
        return None
    if logo.width <= max_width:
        return logo
    scale = max_width / float(logo.width)
    new_width = max(1, int(round(logo.width * scale)))
    new_height = max(1, int(round(logo.height * scale)))
    if new_width == logo.width:
        return logo
    return logo.resize((new_width, new_height), resample=RESAMPLE)


def _paste_possession_icon(canvas: Image.Image, column_idx: int, x_offset: int, y_offset: int):
    icon = _get_possession_icon()
    if icon is None:
        return

    # Calculate column positions relative to x_offset
    col_x = [x_offset + _COL_LEFT]
    for w in COL_WIDTHS:
        col_x.append(col_x[-1] + w)

    column_left = col_x[column_idx]
    column_width = COL_WIDTHS[column_idx]

    x = column_left + column_width - icon.width - 12
    y = y_offset + SCORE_ROW_H - icon.height - 12
    if x < column_left:
        x = column_left
    if y < y_offset:
        y = y_offset

    canvas.paste(icon, (x, y), icon)


def _draw_game_block(canvas: Image.Image, draw: ImageDraw.ImageDraw, game: dict, x_offset: int, y_offset: int):
    """Draw a single game block at the specified offset for dual-game layout."""
    competitors = (game or {}).get("competitors", [])
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})

    show_scores = _should_display_scores(game)
    away_text = _score_text(away, show=show_scores)
    home_text = _score_text(home, show=show_scores)
    in_progress = _is_game_in_progress(game)
    final = _is_game_final(game)
    results = _final_results(away, home) if final else {"away": None, "home": None}
    possession_flags = _team_has_possession(game)

    # Calculate column positions relative to x_offset
    col_x = [x_offset + _COL_LEFT]
    for w in COL_WIDTHS:
        col_x.append(col_x[-1] + w)

    score_top = y_offset
    text_bounds: dict[int, tuple[int, int]] = {}
    score_font = SCORE_FONT if show_scores else STATUS_FONT
    for idx, text in ((0, away_text), (2, "@"), (4, home_text)):
        font = score_font if idx != 2 else CENTER_FONT
        if idx == 0:
            fill = _score_fill("away", in_progress=in_progress, final=final, results=results)
        elif idx == 4:
            fill = _score_fill("home", in_progress=in_progress, final=final, results=results)
        else:
            fill = (255, 255, 255)
        text_width, _ = _measure_text(draw, text, font)
        left = col_x[idx] + (COL_WIDTHS[idx] - text_width) // 2
        text_bounds[idx] = (left, left + text_width)
        _center_text(draw, text, font, col_x[idx], COL_WIDTHS[idx], score_top, SCORE_ROW_H, fill=fill)

    center_left, center_right = text_bounds.get(2, (0, 0))
    away_right = text_bounds.get(0, (0, 0))[1]
    home_left = text_bounds.get(4, (0, 0))[0]
    max_logo_widths = {
        1: _logo_target_width(center_left - away_right, COL_WIDTHS[1]),
        3: _logo_target_width(home_left - center_right, COL_WIDTHS[3]),
    }

    for idx, team_side, team_key in ((1, away, "away"), (3, home, "home")):
        team_obj = (team_side or {}).get("team", {})
        abbr = _team_logo_abbr(team_obj)
        logo = _load_logo_cached(abbr)
        if not logo:
            continue
        max_width = max_logo_widths.get(idx, COL_WIDTHS[idx] - LOGO_GAP_MARGIN)
        fitted_logo = _fit_logo_to_width(logo, max_width)
        if not fitted_logo:
            continue
        x0 = col_x[idx] + (COL_WIDTHS[idx] - fitted_logo.width) // 2
        y0 = score_top + (SCORE_ROW_H - fitted_logo.height) // 2
        canvas.paste(fitted_logo, (x0, y0), fitted_logo)
        if possession_flags.get(team_key):
            _paste_possession_icon(canvas, idx, x_offset, y_offset)

    status_top = score_top + SCORE_ROW_H + STATUS_TEXT_NUDGE
    status_text = _format_status(game)
    status_fill = IN_PROGRESS_STATUS_COLOR if in_progress else (255, 255, 255)
    _center_text(draw, status_text, STATUS_FONT, col_x[2], COL_WIDTHS[2], status_top, STATUS_ROW_H, fill=status_fill)


def _compose_canvas(games: list[dict], *, show_super_bowl: bool = False) -> Image.Image:
    """Compose canvas with dual-game layout (2 games per row)."""
    if not games:
        return Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND_COLOR)

    # Calculate number of rows needed
    num_rows = (len(games) + GAMES_PER_ROW - 1) // GAMES_PER_ROW

    # Calculate total height
    base_height = GAME_HEIGHT * num_rows
    if num_rows > 1:
        base_height += BLOCK_SPACING * (num_rows - 1)
    super_bowl_logo = _get_super_bowl_logo() if show_super_bowl else None
    total_height = base_height
    if super_bowl_logo:
        total_height = base_height + SUPER_BOWL_LOGO_GAP + super_bowl_logo.height

    canvas = Image.new("RGB", (WIDTH, total_height), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(canvas)

    # Draw games in a 2-column grid
    for idx, game in enumerate(games):
        row = idx // GAMES_PER_ROW
        col = idx % GAMES_PER_ROW

        x_offset = col * GAME_WIDTH
        y_offset = row * (GAME_HEIGHT + BLOCK_SPACING)

        _draw_game_block(canvas, draw, game, x_offset, y_offset)

        # Draw vertical separator between columns
        if col == 0 and idx < len(games) - 1:
            sep_x = GAME_WIDTH
            sep_y_start = y_offset + 10
            sep_y_end = y_offset + GAME_HEIGHT - 10
            draw.line((sep_x, sep_y_start, sep_x, sep_y_end), fill=(60, 60, 60), width=2)

        # Draw horizontal separator between rows
        if row < num_rows - 1 and idx >= len(games) - GAMES_PER_ROW - (len(games) % GAMES_PER_ROW):
            pass  # Skip separator after last row
        elif idx < len(games) - GAMES_PER_ROW:
            if col == GAMES_PER_ROW - 1 or idx == len(games) - 1:
                sep_y = y_offset + GAME_HEIGHT + BLOCK_SPACING // 2
                x_start = 30 if col == 0 else x_offset + 30
                x_end = WIDTH - 30 if col == GAMES_PER_ROW - 1 else x_offset + GAME_WIDTH - 30
                draw.line((x_start, sep_y, x_end, sep_y), fill=(45, 45, 45))

    if super_bowl_logo:
        logo_x = (WIDTH - super_bowl_logo.width) // 2
        logo_y = base_height + SUPER_BOWL_LOGO_GAP
        canvas.paste(super_bowl_logo, (logo_x, logo_y), super_bowl_logo)

    return canvas


def _timestamp_to_local(ts: str) -> Optional[datetime.datetime]:
    if not ts:
        return None
    try:
        dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%MZ")
    except ValueError:
        try:
            dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
    dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(CENTRAL_TIME)


def _game_sort_key(game: dict):
    return (
        game.get("_start_sort", float("inf")),
        str(game.get("id") or game.get("uid") or ""),
    )


def _hydrate_games(raw_games: Iterable[dict]) -> list[dict]:
    games: list[dict] = []
    for game in raw_games:
        game = game or {}
        start_local = _timestamp_to_local(game.get("_event_date"))
        if start_local:
            game["_start_local"] = start_local
            game["_start_sort"] = start_local.timestamp()
        else:
            game["_start_sort"] = float("inf")
        games.append(game)
    games.sort(key=_game_sort_key)
    return games


def _fetch_games_for_date(day: datetime.date) -> list[dict]:
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        f"?dates={day.strftime('%Y%m%d')}"
    )
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logging.error("Failed to fetch NFL scoreboard: %s", exc)
        return []

    raw_games: list[dict] = []
    for event in data.get("events", []) or []:
        event_date = event.get("date")
        local_start = _timestamp_to_local(event_date)
        if local_start and local_start.date() != day:
            continue
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        comp = competitions[0] or {}
        comp = dict(comp)
        comp["_event_date"] = event_date
        raw_games.append(comp)
    return _hydrate_games(raw_games)


def _fetch_games_for_week(now: Optional[datetime.datetime] = None) -> list[dict]:
    now = now or datetime.datetime.now(CENTRAL_TIME)
    games: list[dict] = []
    week_dates = _week_dates(now)
    for day in week_dates:
        games.extend(_fetch_games_for_date(day))
    games.sort(key=_game_sort_key)
    if games and _should_advance_playoff_week(now, week_dates[0], len(games)):
        next_week_dates = [day + datetime.timedelta(days=7) for day in week_dates]
        games = []
        for day in next_week_dates:
            games.extend(_fetch_games_for_date(day))
        games.sort(key=_game_sort_key)
    return games


def _render_scoreboard(games: list[dict], *, show_super_bowl: bool = False) -> Image.Image:
    canvas = _compose_canvas(games, show_super_bowl=show_super_bowl)

    dummy = Image.new("RGB", (WIDTH, 10), BACKGROUND_COLOR)
    dd = ImageDraw.Draw(dummy)
    try:
        l, t, r, b = dd.textbbox((0, 0), TITLE, font=TITLE_FONT)
        title_h = b - t
    except Exception:
        _, title_h = dd.textsize(TITLE, font=TITLE_FONT)

    league_logo = _get_league_logo()
    logo_height = league_logo.height if league_logo else 0
    logo_gap = LEAGUE_LOGO_GAP if league_logo else 0

    content_top = logo_height + logo_gap + title_h + TITLE_GAP
    img_height = max(HEIGHT, content_top + canvas.height)
    img = Image.new("RGB", (WIDTH, img_height), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    if league_logo:
        logo_x = (WIDTH - league_logo.width) // 2
        img.paste(league_logo, (logo_x, 0), league_logo)
    title_top = logo_height + logo_gap

    try:
        l, t, r, b = draw.textbbox((0, 0), TITLE, font=TITLE_FONT)
        tw, th = r - l, b - t
        tx = (WIDTH - tw) // 2 - l
        ty = title_top - t
    except Exception:
        tw, th = draw.textsize(TITLE, font=TITLE_FONT)
        tx = (WIDTH - tw) // 2
        ty = title_top
    draw.text((tx, ty), TITLE, font=TITLE_FONT, fill=(255, 255, 255))

    img.paste(canvas, (0, content_top))
    return img


def _scroll_display(display, full_img: Image.Image):
    if full_img.height <= HEIGHT:
        display.image(full_img)
        return

    max_offset = full_img.height - HEIGHT
    frame = full_img.crop((0, 0, WIDTH, HEIGHT))
    display.image(frame)
    time.sleep(SCOREBOARD_SCROLL_PAUSE_TOP)

    for offset in range(
        SCOREBOARD_SCROLL_STEP, max_offset + 1, SCOREBOARD_SCROLL_STEP
    ):
        frame = full_img.crop((0, offset, WIDTH, offset + HEIGHT))
        display.image(frame)
        time.sleep(SCOREBOARD_SCROLL_DELAY)

    time.sleep(SCOREBOARD_SCROLL_PAUSE_BOTTOM)


# ─── Public API ───────────────────────────────────────────────────────────────
@log_call
def draw_nfl_scoreboard_v2(display, transition: bool = False) -> ScreenImage:
    now = datetime.datetime.now(CENTRAL_TIME)
    games = _fetch_games_for_week(now)

    if not games:
        clear_display(display)
        img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)
        league_logo = _get_league_logo()
        title_top = 0
        if league_logo:
            logo_x = (WIDTH - league_logo.width) // 2
            img.paste(league_logo, (logo_x, 0), league_logo)
            title_top = league_logo.height + LEAGUE_LOGO_GAP
        try:
            l, t, r, b = draw.textbbox((0, 0), TITLE, font=TITLE_FONT)
            tw, th = r - l, b - t
            tx = (WIDTH - tw) // 2 - l
            ty = title_top - t
        except Exception:
            tw, th = draw.textsize(TITLE, font=TITLE_FONT)
            tx = (WIDTH - tw) // 2
            ty = title_top
        draw.text((tx, ty), TITLE, font=TITLE_FONT, fill=(255, 255, 255))
        _center_text(draw, "No games", STATUS_FONT, 0, WIDTH, HEIGHT // 2 - STATUS_ROW_H // 2, STATUS_ROW_H)
        if transition:
            return ScreenImage(img, displayed=False)
        display.image(img)
        time.sleep(SCOREBOARD_SCROLL_PAUSE_BOTTOM)
        return ScreenImage(img, displayed=True)

    show_super_bowl = _in_playoff_window(now) and len(games) == 1
    full_img = _render_scoreboard(games, show_super_bowl=show_super_bowl)
    if transition:
        _scroll_display(display, full_img)
        return ScreenImage(full_img, displayed=True)

    if full_img.height <= HEIGHT:
        display.image(full_img)
        time.sleep(SCOREBOARD_SCROLL_PAUSE_BOTTOM)
    else:
        _scroll_display(display, full_img)
    return ScreenImage(full_img, displayed=True)


if __name__ == "__main__":  # pragma: no cover
    from utils import Display

    disp = Display()
    try:
        draw_nfl_scoreboard_v2(disp)
    finally:
        clear_display(disp)
