#!/usr/bin/env python3
"""
nfl_scoreboard.py

Render a scrolling NFL scoreboard mirroring the layout of the MLB board.
Shows all games in the active NFL week (Thursday through Monday). Final scores
persist until Wednesday at 9:00 AM Central before advancing to the next week.
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

from config import (
    WIDTH,
    HEIGHT,
    FONT_TITLE_SPORTS,
    FONT_TEAM_SPORTS,
    FONT_STATUS,
    CENTRAL_TIME,
    IMAGES_DIR,
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
BLOCK_SPACING       = 20
SCORE_ROW_H         = 150
STATUS_ROW_H        = 48
REQUEST_TIMEOUT     = 10

COL_WIDTHS = [120, 170, 100, 170, 120]  # total = 680 (WIDTH)
_TOTAL_COL_WIDTH = sum(COL_WIDTHS)
_COL_LEFT = max(0, (WIDTH - _TOTAL_COL_WIDTH) // 2)
COL_X = [_COL_LEFT]
for w in COL_WIDTHS:
    COL_X.append(COL_X[-1] + w)

SCORE_FONT              = clone_font(FONT_TEAM_SPORTS, 66)
STATUS_FONT             = clone_font(FONT_STATUS, 42)
CENTER_FONT             = clone_font(FONT_STATUS, 54)
TITLE_FONT              = FONT_TITLE_SPORTS
LOGO_HEIGHT             = 150
LOGO_DIR                = os.path.join(IMAGES_DIR, "nfl")
LEAGUE_LOGO_KEYS        = ("NFL", "nfl")
LEAGUE_LOGO_GAP         = 10
LEAGUE_LOGO_HEIGHT      = max(1, int(round(LOGO_HEIGHT * 1.35)))
IN_PROGRESS_SCORE_COLOR = SCOREBOARD_IN_PROGRESS_SCORE_COLOR
IN_PROGRESS_STATUS_COLOR = IN_PROGRESS_SCORE_COLOR
FINAL_WINNING_SCORE_COLOR = SCOREBOARD_FINAL_WINNING_SCORE_COLOR
FINAL_LOSING_SCORE_COLOR = SCOREBOARD_FINAL_LOSING_SCORE_COLOR
BACKGROUND_COLOR = SCOREBOARD_BACKGROUND_COLOR

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


# ─── Helpers ──────────────────────────────────────────────────────────────────
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
                _LEAGUE_LOGO = logo
                break
        _LEAGUE_LOGO_LOADED = True
    return _LEAGUE_LOGO


def _get_possession_icon() -> Optional[Image.Image]:
    global _POSSESSION_ICON
    if _POSSESSION_ICON is not None:
        return _POSSESSION_ICON

    try:
        height = max(14, LOGO_HEIGHT // 5)
        width = max(10, int(round(height * 1.6)))
        icon = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(icon)

        pad_y = max(1, height // 6)
        outline = max(1, height // 7)
        body_color = (154, 93, 48)
        stripe_color = (255, 255, 255)

        draw.ellipse(
            (0, pad_y, width - 1, height - pad_y - 1),
            fill=body_color,
            outline=stripe_color,
            width=outline,
        )

        stripe_margin = max(1, width // 6)
        stripe_width = max(1, width // 18)
        draw.line(
            (stripe_margin, pad_y + 1, stripe_margin, height - pad_y - 2),
            fill=stripe_color,
            width=stripe_width,
        )
        draw.line(
            (width - stripe_margin - 1, pad_y + 1, width - stripe_margin - 1, height - pad_y - 2),
            fill=stripe_color,
            width=stripe_width,
        )

        lace_y = (pad_y + height - pad_y - 1) // 2
        lace_half = max(1, width // 6)
        draw.line(
            (width // 2 - lace_half, lace_y, width // 2 + lace_half, lace_y),
            fill=stripe_color,
            width=max(1, height // 6),
        )

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
        return "—"
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


def _paste_possession_icon(canvas: Image.Image, column_idx: int, top: int):
    icon = _get_possession_icon()
    if icon is None:
        return

    column_left = COL_X[column_idx]
    column_width = COL_WIDTHS[column_idx]

    x = column_left + column_width - icon.width - 12
    y = top + SCORE_ROW_H - icon.height - 12
    if x < column_left:
        x = column_left
    if y < top:
        y = top

    canvas.paste(icon, (x, y), icon)


def _draw_game_block(canvas: Image.Image, draw: ImageDraw.ImageDraw, game: dict, top: int):
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

    score_top = top
    for idx, text in ((0, away_text), (2, "@"), (4, home_text)):
        font = SCORE_FONT if idx != 2 else CENTER_FONT
        if idx == 0:
            fill = _score_fill("away", in_progress=in_progress, final=final, results=results)
        elif idx == 4:
            fill = _score_fill("home", in_progress=in_progress, final=final, results=results)
        else:
            fill = (255, 255, 255)
        _center_text(draw, text, font, COL_X[idx], COL_WIDTHS[idx], score_top, SCORE_ROW_H, fill=fill)

    for idx, team_side, team_key in ((1, away, "away"), (3, home, "home")):
        team_obj = (team_side or {}).get("team", {})
        abbr = _team_logo_abbr(team_obj)
        logo = _load_logo_cached(abbr)
        if not logo:
            continue
        x0 = COL_X[idx] + (COL_WIDTHS[idx] - logo.width) // 2
        y0 = score_top + (SCORE_ROW_H - logo.height) // 2
        canvas.paste(logo, (x0, y0), logo)
        if possession_flags.get(team_key):
            _paste_possession_icon(canvas, idx, score_top)

    status_top = score_top + SCORE_ROW_H
    status_text = _format_status(game)
    status_fill = IN_PROGRESS_STATUS_COLOR if in_progress else (255, 255, 255)
    _center_text(draw, status_text, STATUS_FONT, COL_X[2], COL_WIDTHS[2], status_top, STATUS_ROW_H, fill=status_fill)


def _compose_canvas(games: list[dict]) -> Image.Image:
    if not games:
        return Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND_COLOR)
    block_height = SCORE_ROW_H + STATUS_ROW_H
    total_height = block_height * len(games)
    if len(games) > 1:
        total_height += BLOCK_SPACING * (len(games) - 1)
    canvas = Image.new("RGB", (WIDTH, total_height), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(canvas)

    y = 0
    for idx, game in enumerate(games):
        _draw_game_block(canvas, draw, game, y)
        y += SCORE_ROW_H + STATUS_ROW_H
        if idx < len(games) - 1:
            sep_y = y + BLOCK_SPACING // 2
            draw.line((30, sep_y, WIDTH - 30, sep_y), fill=(45, 45, 45))
            y += BLOCK_SPACING
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
    games: list[dict] = []
    for day in _week_dates(now):
        games.extend(_fetch_games_for_date(day))
    games.sort(key=_game_sort_key)
    return games


def _render_scoreboard(games: list[dict]) -> Image.Image:
    canvas = _compose_canvas(games)

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
def draw_nfl_scoreboard(display, transition: bool = False) -> ScreenImage:
    games = _fetch_games_for_week()

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

    full_img = _render_scoreboard(games)
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
        draw_nfl_scoreboard(disp)
    finally:
        clear_display(disp)
