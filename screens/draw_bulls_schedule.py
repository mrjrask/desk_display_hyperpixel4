#!/usr/bin/env python3
"""draw_bulls_schedule.py

Chicago Bulls schedule screens mirroring the Blackhawks layout: last game,
live game, next game, and next home game cards with NBA logos.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
from config import (
    FONT_DATE_SPORTS,
    FONT_TEAM_SPORTS,
    FONT_TITLE_SPORTS,
    NBA_IMAGES_DIR,
    NBA_TEAM_ID,
    NBA_TEAM_TRICODE,
    NEXT_GAME_LOGO_FONT_SIZE,
    TIMES_SQUARE_FONT_PATH,
    WIDTH,
    HEIGHT,
    CENTRAL_TIME,
)

from utils import clear_display, load_team_logo

TS_PATH = TIMES_SQUARE_FONT_PATH
NBA_DIR = NBA_IMAGES_DIR
BULLS_TEAM_ID = str(NBA_TEAM_ID)
BULLS_TRICODE = (NBA_TEAM_TRICODE or "CHI").upper()


def _ts(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(TS_PATH, size)
    except Exception:
        logging.warning("TimesSquare font missing at %s; using default.", TS_PATH)
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()


_ABBR_BASE = 33 if HEIGHT > 64 else 30
_SCORE_BASE = 30 if HEIGHT > 64 else 26

_ABBR_FONT_SIZE = int(round(_ABBR_BASE * 1.3))
_SCORE_FONT_SIZE = int(round(_SCORE_BASE * 1.45))

FONT_ABBR = _ts(_ABBR_FONT_SIZE)
FONT_SCORE = _ts(_SCORE_FONT_SIZE)
FONT_SMALL = _ts(22 if HEIGHT > 64 else 19)

FONT_TITLE = FONT_TITLE_SPORTS
FONT_BOTTOM = FONT_DATE_SPORTS
FONT_NEXT_OPP = FONT_TEAM_SPORTS

BOTTOM_LABEL_MARGIN = 8
BACKGROUND_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)

_LOGO_CACHE: Dict[Tuple[str, int], Optional[Image.Image]] = {}


def _load_logo_cached(abbr: str, height: int) -> Optional[Image.Image]:
    key = ((abbr or "").upper(), height)
    if key in _LOGO_CACHE:
        logo = _LOGO_CACHE[key]
        return logo.copy() if logo else None

    logo = load_team_logo(NBA_DIR, key[0], height=height)
    if logo is None and key[0] != "NBA":
        logo = load_team_logo(NBA_DIR, "NBA", height=height)
    _LOGO_CACHE[key] = logo
    return logo.copy() if logo else None


def _text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int, int, int]:
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    except Exception:
        width, height = draw.textsize(text, font=font)
        left, top = 0, 0
        right, bottom = width, height
    return left, top, right, bottom


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    left, _, right, _ = _text_bbox(draw, text, font)
    return right - left


def _text_h(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont) -> int:
    _, _, _, bottom = _text_bbox(draw, "Hg", font)
    return bottom


def _center_text(draw: ImageDraw.ImageDraw, y: int, text: str, font: ImageFont.ImageFont, *, fill=TEXT_COLOR) -> None:
    if not text:
        return
    width = _text_w(draw, text, font)
    x = (WIDTH - width) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _center_wrapped_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    *,
    max_width: Optional[int] = None,
    line_spacing: int = 1,
) -> int:
    if not text:
        return 0

    max_width = min(max_width or WIDTH, WIDTH)
    text_height = _text_h(draw, font)

    if _text_w(draw, text, font) <= max_width:
        _center_text(draw, y, text, font)
        return text_height

    words = text.split()
    if not words:
        return 0

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}" if current else word
        if _text_w(draw, candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    fixed_lines = []
    for line in lines:
        if _text_w(draw, line, font) <= max_width:
            fixed_lines.append(line)
            continue
        chunk = ""
        for ch in line:
            test = f"{chunk}{ch}"
            if chunk and _text_w(draw, test, font) > max_width:
                fixed_lines.append(chunk)
                chunk = ch
            else:
                chunk = test
        if chunk:
            fixed_lines.append(chunk)

    lines = fixed_lines or lines

    total_height = 0
    for idx, line in enumerate(lines):
        line_y = y + idx * (text_height + line_spacing)
        _center_text(draw, line_y, line, font)
        total_height = (idx + 1) * text_height + idx * line_spacing

    return total_height


def _draw_title_line(draw: ImageDraw.ImageDraw, y: int, text: str) -> int:
    if not text:
        return 0
    _center_text(draw, y, text, FONT_TITLE)
    return _text_h(draw, FONT_TITLE)


def _parse_datetime(value: str) -> Optional[dt.datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            parsed = dt.datetime.strptime(text, fmt)
        except Exception:
            continue
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(CENTRAL_TIME)
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(CENTRAL_TIME)


def _get_local_start(game: Dict) -> Optional[dt.datetime]:
    start = game.get("_start_local")
    if isinstance(start, dt.datetime):
        return start.astimezone(CENTRAL_TIME) if start.tzinfo else CENTRAL_TIME.localize(start)
    return _parse_datetime(game.get("gameDate"))


def _get_official_date(game: Dict) -> Optional[dt.date]:
    official = game.get("officialDate")
    if isinstance(official, str) and official:
        try:
            return dt.date.fromisoformat(official[:10])
        except ValueError:
            pass
    start = _get_local_start(game)
    return start.date() if isinstance(start, dt.datetime) else None


def _relative_label(date_obj: Optional[dt.date]) -> str:
    if not isinstance(date_obj, dt.date):
        return ""
    today = dt.datetime.now(CENTRAL_TIME).date()
    if date_obj == today:
        return "Today"
    if date_obj == today + dt.timedelta(days=1):
        return "Tomorrow"
    if date_obj == today - dt.timedelta(days=1):
        return "Yesterday"
    fmt = "%a %b %-d" if os.name != "nt" else "%a %b %#d"
    return date_obj.strftime(fmt)


def _format_time(start: Optional[dt.datetime]) -> str:
    if not isinstance(start, dt.datetime):
        return ""
    fmt = "%-I:%M %p" if os.name != "nt" else "%#I:%M %p"
    return start.strftime(fmt).replace(" 0", " ").lstrip("0")


def _team_entry(game: Dict, side: str) -> Dict[str, Optional[str]]:
    teams = game.get("teams") or {}
    entry = teams.get(side) or {}
    team_info = entry.get("team") if isinstance(entry.get("team"), dict) else {}
    tri = (team_info.get("triCode") or team_info.get("abbreviation") or "").upper()
    name = team_info.get("name") or ""
    team_id = str(team_info.get("id") or "")
    score_raw = entry.get("score")
    try:
        score = int(score_raw)
    except (TypeError, ValueError):
        score = None
    return {
        "tri": tri,
        "name": name,
        "id": team_id,
        "score": score,
    }


def _is_bulls_side(entry: Dict[str, Optional[str]]) -> bool:
    return (entry.get("id") and entry["id"] == BULLS_TEAM_ID) or (entry.get("tri") and entry["tri"].upper() == BULLS_TRICODE)


def _game_state(game: Dict) -> str:
    status = game.get("status") or {}
    abstract = str(status.get("abstractGameState") or "").lower()
    if abstract:
        return abstract
    detailed = str(status.get("detailedState") or "").lower()
    if "final" in detailed:
        return "final"
    if "live" in detailed or "progress" in detailed:
        return "live"
    if "preview" in detailed or "schedule" in detailed or "pregame" in detailed:
        return "preview"
    code = str(status.get("statusCode") or "")
    if code == "3":
        return "final"
    if code == "2":
        return "live"
    if code == "1":
        return "preview"
    return detailed


def _status_text(game: Dict) -> str:
    status = game.get("status") or {}
    return str(status.get("detailedState") or status.get("abstractGameState") or "").strip()


def _live_status(game: Dict) -> str:
    linescore = game.get("linescore") or {}
    clock = (linescore.get("currentPeriodTimeRemaining") or "").strip()
    period = (linescore.get("currentPeriodOrdinal") or "").strip()
    pieces = [piece for piece in (clock, period) if piece]
    if not pieces:
        return _status_text(game) or "Live"
    return " • ".join(pieces)


def _render_message(title: str, message: str) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    y = 2
    y += _draw_title_line(draw, title)
    y += 4
    _center_wrapped_text(draw, y, message, FONT_BOTTOM, max_width=WIDTH - 8)
    return img


def _draw_scoreboard(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    top_y: int,
    away: Dict[str, Optional[str]],
    home: Dict[str, Optional[str]],
    *,
    bottom_reserved_px: int = 0,
) -> int:
    col1_w = min(WIDTH - 24, max(84, int(WIDTH * 0.72)))
    col2_w = WIDTH - col1_w
    x0, x1 = 0, col1_w

    total_available = max(0, HEIGHT - bottom_reserved_px - top_y)
    row_h = max(total_available // 2, 32) if total_available else 32
    row_h = min(row_h, 56)
    if row_h * 2 > total_available and total_available > 0:
        row_h = max(24, total_available // 2)
    if row_h <= 0:
        row_h = 32

    table_height = row_h * 2
    if total_available:
        table_height = min(table_height, total_available)
    if table_height < 2:
        table_height = 2

    row_area_height = table_height
    row1_h = max(1, row_area_height // 2)
    row2_h = max(1, row_area_height - row1_h)

    row1_top = top_y
    row2_top = row1_top + row1_h

    def _prepare(info: Dict[str, Optional[str]], top: int, height: int) -> Dict:
        tri = (info.get("tri") or "").upper()
        score = info.get("score")
        logo_height = max(1, min(height - 4, 64))
        logo = _load_logo_cached(tri, logo_height)
        text = info.get("name") or tri or "—"
        logo_w = logo.width if logo else 0
        text_start = x0 + 6 + (logo_w + 6 if logo else 0)
        max_width = max(1, x1 - text_start - 4)
        return {
            "tri": tri,
            "score": score,
            "logo": logo,
            "text": text,
            "top": top,
            "height": height,
            "max_width": max_width,
        }

    specs = [
        _prepare(away, row1_top, row1_h),
        _prepare(home, row2_top, row2_h),
    ]

    def _fits(font: ImageFont.ImageFont) -> bool:
        for spec in specs:
            if not spec["text"]:
                continue
            if _text_w(draw, spec["text"], font) > spec["max_width"]:
                return False
        return True

    name_font = FONT_ABBR
    if not _fits(name_font):
        size = getattr(FONT_ABBR, "size", None) or _ABBR_FONT_SIZE
        min_size = max(8, int(round(_ABBR_FONT_SIZE * 0.5)))
        chosen = None
        for test in range(size - 1, min_size - 1, -1):
            candidate = _ts(test)
            if _fits(candidate):
                chosen = candidate
                break
        name_font = chosen or _ts(min_size)

    for spec in specs:
        cy = spec["top"] + spec["height"] // 2
        lx = x0 + 6
        if spec["logo"] is not None:
            logo = spec["logo"]
            lw, lh = logo.size
            ly = cy - lh // 2
            try:
                img.paste(logo, (lx, ly), logo)
            except Exception:
                pass
            lx += lw + 6

        text = spec["text"] or "—"
        max_width = spec["max_width"]
        if _text_w(draw, text, name_font) > max_width:
            ellipsis = "…"
            trimmed = text
            while trimmed and _text_w(draw, trimmed + ellipsis, name_font) > max_width:
                trimmed = trimmed[:-1]
            text = (trimmed + ellipsis) if trimmed else ellipsis

        text_h = _text_h(draw, name_font)
        ty = cy - text_h // 2
        draw.text((lx, ty), text, font=name_font, fill=TEXT_COLOR)

        score = spec["score"]
        score_txt = "-" if score is None else str(score)
        sw = _text_w(draw, score_txt, FONT_SCORE)
        sh = _text_h(draw, FONT_SCORE)
        sx = x1 + (col2_w - sw) // 2
        sy = cy - sh // 2
        draw.text((sx, sy), score_txt, font=FONT_SCORE, fill=TEXT_COLOR)

    return row2_top + row2_h


def _render_scoreboard(
    game: Dict,
    *,
    title: str,
    footer: str,
    inline_status: str = "",
) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    y = 2
    y += _draw_title_line(draw, title)

    if inline_status:
        y += 1
        _center_text(draw, y, inline_status, FONT_SMALL)
        y += _text_h(draw, FONT_SMALL)

    bottom_text = footer.strip()
    reserve = (_text_h(draw, FONT_BOTTOM) + BOTTOM_LABEL_MARGIN) if bottom_text else 0

    away = _team_entry(game, "away")
    home = _team_entry(game, "home")
    _draw_scoreboard(img, draw, y + 2, away, home, bottom_reserved_px=reserve)

    if bottom_text:
        by = HEIGHT - _text_h(draw, FONT_BOTTOM) - BOTTOM_LABEL_MARGIN
        _center_text(draw, by, bottom_text, FONT_BOTTOM)

    return img


def _format_footer_last(game: Dict) -> str:
    date_obj = _get_official_date(game)
    label = _relative_label(date_obj)
    if label:
        return label
    if isinstance(date_obj, dt.date):
        fmt = "%a, %b %-d" if os.name != "nt" else "%a, %b %#d"
        return date_obj.strftime(fmt)
    return ""


def _format_footer_next(game: Dict) -> str:
    start = _get_local_start(game)
    if isinstance(start, dt.datetime):
        date_fmt = "%a, %b %-d" if os.name != "nt" else "%a, %b %#d"
        time_fmt = "%-I:%M %p" if os.name != "nt" else "%#I:%M %p"
        date_part = start.strftime(date_fmt)
        time_part = start.strftime(time_fmt).replace(" 0", " ").lstrip("0")
        return f"{date_part} · {time_part}"

    label = _relative_label(_get_official_date(game))
    return label


def _format_matchup_line(game: Dict) -> str:
    away = _team_entry(game, "away")
    home = _team_entry(game, "home")
    bulls_home = _is_bulls_side(home)
    opponent = away if bulls_home else home
    prefix = "vs." if bulls_home else "@"
    return f"{prefix} {opponent.get('name') or opponent.get('tri') or ''}".strip()


def _render_next_game(game: Dict, *, title: str) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    y = 2
    y += _draw_title_line(draw, title)
    y += 1

    matchup = _format_matchup_line(game)
    matchup_height = _center_wrapped_text(draw, y, matchup, FONT_NEXT_OPP, max_width=WIDTH - 6)
    y += matchup_height + 2 if matchup_height else _text_h(draw, FONT_NEXT_OPP) + 2

    away = _team_entry(game, "away")
    home = _team_entry(game, "home")
    away_logo = _load_logo_cached(away.get("tri"), NEXT_GAME_LOGO_FONT_SIZE)
    home_logo = _load_logo_cached(home.get("tri"), NEXT_GAME_LOGO_FONT_SIZE)

    bottom_text = _format_footer_next(game)
    bottom_h = _text_h(draw, FONT_BOTTOM) if bottom_text else 0
    bottom_y = HEIGHT - (bottom_h + BOTTOM_LABEL_MARGIN) if bottom_text else HEIGHT

    available_h = max(10, bottom_y - (y + 2))
    logo_h = max(1, min(NEXT_GAME_LOGO_FONT_SIZE, available_h))

    def _resize_logo(logo: Optional[Image.Image]) -> Optional[Image.Image]:
        if logo is None:
            return None
        try:
            w, h = logo.size
            if h == logo_h:
                return logo
            r = logo_h / float(h)
            return logo.resize((max(1, int(round(w * r))), logo_h), Image.LANCZOS)
        except Exception:
            return logo

    away_logo = _resize_logo(away_logo)
    home_logo = _resize_logo(home_logo)

    at_txt = "@"
    at_w = _text_w(draw, at_txt, FONT_NEXT_OPP)
    at_h = _text_h(draw, FONT_NEXT_OPP)
    row_top = y + 2
    row_height = logo_h

    total_width = (away_logo.width if away_logo else 0) + (home_logo.width if home_logo else 0) + at_w + 24
    start_x = max(0, (WIDTH - total_width) // 2)

    cy = row_top + row_height // 2

    if away_logo:
        ay = cy - away_logo.height // 2
        img.paste(away_logo, (start_x, ay), away_logo)
        start_x += away_logo.width + 12
    else:
        tri = away.get("tri") or "AWY"
        draw.text((start_x, cy - _text_h(draw, FONT_NEXT_OPP) // 2), tri, font=FONT_NEXT_OPP, fill=TEXT_COLOR)
        start_x += _text_w(draw, tri, FONT_NEXT_OPP) + 12

    at_x = start_x
    at_y = cy - at_h // 2
    draw.text((at_x, at_y), at_txt, font=FONT_NEXT_OPP, fill=TEXT_COLOR)
    start_x += at_w + 12

    if home_logo:
        hy = cy - home_logo.height // 2
        img.paste(home_logo, (start_x, hy), home_logo)
    else:
        tri = home.get("tri") or "HOME"
        draw.text((start_x, cy - _text_h(draw, FONT_NEXT_OPP) // 2), tri, font=FONT_NEXT_OPP, fill=TEXT_COLOR)

    if bottom_text:
        by = HEIGHT - _text_h(draw, FONT_BOTTOM) - BOTTOM_LABEL_MARGIN
        _center_text(draw, by, bottom_text, FONT_BOTTOM)

    return img


def _push(display, img: Optional[Image.Image], *, transition: bool = False) -> Optional[Image.Image]:
    if img is None or display is None:
        return None
    if transition:
        return img
    try:
        clear_display(display)
    except Exception:
        pass
    try:
        if hasattr(display, "image"):
            display.image(img)
        elif hasattr(display, "ShowImage"):
            buf = display.getbuffer(img) if hasattr(display, "getbuffer") else img
            display.ShowImage(buf)
        elif hasattr(display, "display"):
            display.display(img)
    except Exception as exc:
        logging.exception("Failed to push Bulls screen: %s", exc)
    return None


def draw_last_bulls_game(display, game: Optional[Dict], transition: bool = False):
    if not game:
        logging.warning("bulls last: no data")
        img = _render_message("Last Bulls game:", "No results available")
        return _push(display, img, transition=transition)

    footer = _format_footer_last(game)
    img = _render_scoreboard(game, title="Last Bulls game:", footer=footer)
    return _push(display, img, transition=transition)


def draw_live_bulls_game(display, game: Optional[Dict], transition: bool = False):
    if not game:
        logging.info("bulls live: no live game")
        img = _render_message("Bulls Live:", "Not in progress")
        return _push(display, img, transition=transition)

    if _game_state(game) != "live":
        logging.info("bulls live: game not live (state=%s)", _game_state(game))
        img = _render_message("Bulls Live:", "Not in progress")
        return _push(display, img, transition=transition)

    footer = _relative_label(_get_official_date(game))
    img = _render_scoreboard(game, title="Bulls Live:", footer=footer, inline_status=_live_status(game))
    return _push(display, img, transition=transition)


def draw_sports_screen_bulls(display, game: Optional[Dict], transition: bool = False):
    if not game:
        logging.warning("bulls next: no upcoming game")
        img = _render_message("Next Bulls game:", "No upcoming game found")
        return _push(display, img, transition=transition)

    img = _render_next_game(game, title="Next Bulls game:")
    return _push(display, img, transition=transition)


def draw_bulls_next_home_game(display, game: Optional[Dict], transition: bool = False):
    if not game:
        logging.info("bulls next home: no upcoming home game")
        img = _render_message("Next at home...", "No United Center games scheduled")
        return _push(display, img, transition=transition)

    img = _render_next_game(game, title="Next at home...")
    return _push(display, img, transition=transition)
