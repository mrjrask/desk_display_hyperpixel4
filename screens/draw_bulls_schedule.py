#!/usr/bin/env python3
"""draw_bulls_schedule.py

Chicago Bulls schedule screens mirroring the Blackhawks layout: last game,
live game, next game, and next home game cards with NBA logos.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any, Dict, Optional, Tuple

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


def _join_dateline_parts(*parts: Optional[str]) -> str:
    pieces = []
    for part in parts:
        if not isinstance(part, str):
            continue
        text = part.strip()
        if text:
            pieces.append(text)
    return " • ".join(pieces)


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


def _record_text_from_entry(entry: Dict[str, Any]) -> str:
    if not isinstance(entry, dict):
        return ""

    def _coerce_record_text(data: Any) -> str:
        if isinstance(data, dict):
            wins = data.get("wins") or data.get("win")
            losses = data.get("losses") or data.get("loss")
            ties = data.get("ties") or data.get("tie") or data.get("draws")
            ot = data.get("ot") or data.get("overtime")
            if wins is not None and losses is not None:
                wins_txt = str(wins).strip()
                losses_txt = str(losses).strip()
                if wins_txt and losses_txt:
                    extra = ""
                    extra_val = ties if ties is not None else ot
                    if extra_val is not None:
                        extra_txt = str(extra_val).strip()
                        if extra_txt:
                            extra = f"-{extra_txt}"
                    return f"{wins_txt}-{losses_txt}{extra}"
            for key in ("displayValue", "summary", "text", "overall"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        elif isinstance(data, str) and data.strip():
            return data.strip()
        return ""

    candidates = []
    for key in ("leagueRecord", "seriesRecord", "record", "overallRecord", "teamRecord"):
        candidates.append(entry.get(key))

    team_info = entry.get("team") if isinstance(entry.get("team"), dict) else {}
    if isinstance(team_info, dict):
        for key in ("leagueRecord", "record", "overallRecord"):
            candidates.append(team_info.get(key))

    for data in candidates:
        text = _coerce_record_text(data)
        if text:
            return text
    return ""


def _team_nickname(team_info: Dict[str, Any], *, fallback: str = "") -> str:
    if not isinstance(team_info, dict):
        return fallback

    def _clean(value: Optional[str]) -> str:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        return ""

    for key in ("teamName", "nickname", "shortDisplayName", "shortName"):
        text = _clean(team_info.get(key))
        if text:
            return text

    display = _clean(team_info.get("displayName"))
    location = _clean(team_info.get("location")) or _clean(team_info.get("city")) or _clean(team_info.get("market"))
    name = _clean(team_info.get("name"))

    def _without_location(text: str) -> str:
        if not text:
            return ""
        lowered = text.lower()
        if location and lowered.startswith(location.lower()):
            trimmed = text[len(location) :].strip(" -")
            if trimmed:
                return trimmed
        return ""

    trimmed_display = _without_location(display)
    if trimmed_display:
        return trimmed_display

    trimmed_name = _without_location(name)
    if trimmed_name:
        return trimmed_name

    if name:
        parts = name.split()
        if len(parts) > 1:
            return " ".join(parts[1:]).strip()
        return name

    if display:
        parts = display.split()
        if len(parts) > 1:
            return " ".join(parts[1:]).strip()
        return display

    return fallback


def _team_entry(game: Dict, side: str) -> Dict[str, Optional[str]]:
    teams = game.get("teams") or {}
    entry = teams.get(side) or {}
    team_info = entry.get("team") if isinstance(entry.get("team"), dict) else {}
    tri = (team_info.get("triCode") or team_info.get("abbreviation") or "").upper()
    name = team_info.get("name") or ""
    nickname = _team_nickname(team_info, fallback=name or tri)
    team_id = str(team_info.get("id") or "")
    score_raw = entry.get("score")
    try:
        score = int(score_raw)
    except (TypeError, ValueError):
        score = None
    return {
        "tri": tri,
        "name": name,
        "nickname": nickname,
        "id": team_id,
        "score": score,
        "record": _record_text_from_entry(entry),
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


def _render_message(title: str, message: str) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    y = 2
    y += _draw_title_line(draw, y, title)
    y += 4
    _center_wrapped_text(draw, y, message, FONT_BOTTOM, max_width=WIDTH - 8)
    return img


def _team_scoreboard_label(team: Dict[str, Optional[str]]) -> str:
    label = (team.get("nickname") or "").strip()
    if label:
        return label
    name = (team.get("name") or "").strip()
    if name:
        return name
    tri = (team.get("tri") or "").strip()
    if tri:
        return tri
    return "—"


def _ellipsize_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if _text_w(draw, text, font) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and _text_w(draw, trimmed + ellipsis, font) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ellipsis) if trimmed else ellipsis


def _draw_scoreboard(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    top_y: int,
    away: Dict[str, Optional[str]],
    home: Dict[str, Optional[str]],
    *,
    bottom_reserved_px: int = 0,
) -> int:
    padding_x = 18
    row_gap = 8
    bottom_limit = HEIGHT - bottom_reserved_px
    available = max(0, bottom_limit - top_y)

    min_row_height = max(68, int(round(HEIGHT * 0.18)))
    preferred_row_height = int(round(HEIGHT * 0.24))
    row_h = max(min_row_height, preferred_row_height)
    if available:
        row_h = min(row_h, max(min_row_height, available // 2))
    total_height = row_h * 2 + row_gap
    if available and total_height > available:
        row_h = max(min_row_height, (available - row_gap) // 2)
        total_height = row_h * 2 + row_gap

    table_top = top_y
    if available and total_height < available:
        table_top += (available - total_height) // 2
    table_bottom = min(bottom_limit, table_top + total_height)

    score_font_size = max(38, int(round(row_h * 0.6)))
    name_font_size = max(26, int(round(row_h * 0.42)))
    min_name_size = max(20, int(round(row_h * 0.32)))
    abbr_font_size = max(24, int(round(row_h * 0.45)))

    score_font = _ts(score_font_size)
    abbr_font = _ts(abbr_font_size)

    def _row_spec(team: Dict[str, Optional[str]], row_top: int) -> Dict[str, Any]:
        tri = (team.get("tri") or "").upper()
        logo_height = max(36, int(round(row_h * 0.7)))
        logo = _load_logo_cached(tri, logo_height)
        label = _team_scoreboard_label(team)
        score = team.get("score")
        return {
            "tri": tri,
            "logo": logo,
            "label": label,
            "score": score,
            "top": row_top,
        }

    row1_top = table_top
    row2_top = table_top + row_h + row_gap
    specs = [
        _row_spec(away, row1_top),
        _row_spec(home, row2_top),
    ]

    score_right = WIDTH - padding_x
    for spec in specs:
        row_top = spec["top"]
        cy = row_top + row_h // 2

        logo = spec["logo"]
        text_x = padding_x
        if logo is not None:
            lw, lh = logo.size
            ly = cy - lh // 2
            try:
                img.paste(logo, (text_x, ly), logo)
            except Exception:
                pass
            text_x += lw + 12
        else:
            abbr = spec["tri"] or "—"
            abbr_w = _text_w(draw, abbr, abbr_font)
            abbr_h = _text_h(draw, abbr_font)
            ax = text_x
            ay = cy - abbr_h // 2
            draw.text((ax, ay), abbr, font=abbr_font, fill=TEXT_COLOR)
            text_x += abbr_w + 12

        score = spec["score"]
        score_txt = "-" if score is None else str(score)
        score_w = _text_w(draw, score_txt, score_font)
        score_h = _text_h(draw, score_font)
        score_x = score_right - score_w
        min_gap = 24
        if score_x - text_x < min_gap:
            score_x = text_x + min_gap
            if score_x + score_w > score_right:
                score_x = score_right - score_w
        score_y = cy - score_h // 2
        draw.text((score_x, score_y), score_txt, font=score_font, fill=TEXT_COLOR)

        label_max_w = max(0, score_x - 12 - text_x)
        label_text = spec["label"] or "—"
        if label_max_w > 0 and label_text:
            current_size = name_font_size
            label_font = _ts(current_size)
            while current_size > min_name_size and _text_w(draw, label_text, label_font) > label_max_w:
                current_size -= 1
                label_font = _ts(current_size)
            label_text = _ellipsize_text(draw, label_text, label_font, label_max_w)
            label_w = _text_w(draw, label_text, label_font)
            label_h = _text_h(draw, label_font)
            label_x = text_x
            label_y = cy - label_h // 2
            draw.text((label_x, label_y), label_text, font=label_font, fill=TEXT_COLOR)

    return table_bottom


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
    y += _draw_title_line(draw, y, title)

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
    date_text = _format_game_date(game)
    status_text = _final_status_label(game)
    return _join_dateline_parts(date_text, status_text)


def _format_footer_next(game: Dict) -> str:
    start = _get_local_start(game)
    if isinstance(start, dt.datetime):
        date_fmt = "%a, %b %-d" if os.name != "nt" else "%a, %b %#d"
        time_fmt = "%-I:%M %p" if os.name != "nt" else "%#I:%M %p"
        date_part = start.strftime(date_fmt)
        time_part = start.strftime(time_fmt).replace(" 0", " ").lstrip("0")
        return _join_dateline_parts(date_part, time_part)

    label = _relative_label(_get_official_date(game))
    return label


def _format_game_date(game: Dict) -> str:
    date_obj = _get_official_date(game)
    if isinstance(date_obj, dt.date):
        fmt = "%a, %b %-d" if os.name != "nt" else "%a, %b %#d"
        return date_obj.strftime(fmt)
    return ""


def _final_status_label(game: Dict) -> str:
    status = game.get("status") or {}
    status_type = status.get("type") if isinstance(status.get("type"), dict) else {}

    text = _status_text(game)
    if isinstance(status_type, dict):
        for key in ("shortDetail", "detail", "description", "name"):
            value = status_type.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break

    if isinstance(text, str):
        upper = text.upper().strip()
        if upper.startswith("FINAL"):
            suffix = upper[5:].strip()
            suffix = suffix.replace("OVERTIME", "OT")
            suffix = suffix.replace(" ", "")
            if suffix and not suffix.startswith("/"):
                suffix = f"/{suffix}"
            return f"F{suffix}" if suffix else "F"
        if upper == "F" or upper.startswith("F/"):
            return upper

    linescore = game.get("linescore") or {}
    final_period = linescore.get("finalPeriod") or linescore.get("currentPeriod")
    try:
        period_val = int(final_period)
    except (TypeError, ValueError):
        period_val = None
    if isinstance(period_val, int) and period_val > 4:
        ot = period_val - 4
        if ot <= 1:
            return "F/OT"
        return f"F/{ot}OT"

    return "F"


def _format_footer_live(game: Dict) -> str:
    linescore = game.get("linescore") or {}
    period = (linescore.get("currentPeriodOrdinal") or "").strip()
    clock = (linescore.get("currentPeriodTimeRemaining") or "").strip()
    pieces = [piece for piece in (period, clock) if piece]
    if pieces:
        return " • ".join(pieces)
    return _status_text(game)


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
    y += _draw_title_line(draw, y, title)
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
    max_logo_height = max(36, min(available_h, int(round(HEIGHT * 0.6))))
    base_away_logo = _load_logo_cached(away.get("tri"), max_logo_height)
    base_home_logo = _load_logo_cached(home.get("tri"), max_logo_height)

    at_txt = "@"
    at_w = _text_w(draw, at_txt, FONT_NEXT_OPP)
    max_width = WIDTH - 24
    spacing_ratio = 0.16

    def _scaled(logo: Optional[Image.Image], height: int) -> Optional[Image.Image]:
        if logo is None:
            return None
        if logo.height == height:
            return logo
        ratio = height / float(logo.height)
        return logo.resize((max(1, int(round(logo.width * ratio))), height), Image.LANCZOS)

    def _text_width(text: str) -> int:
        return _text_w(draw, text, FONT_NEXT_OPP)

    min_height = 34
    best_layout: Optional[tuple[int, int, Optional[Image.Image], Optional[Image.Image]]] = None
    starting_height = min(max_logo_height, max(min_height, available_h))
    for test_h in range(int(starting_height), min_height - 1, -2):
        spacing = max(12, int(round(test_h * spacing_ratio)))
        away_option = _scaled(base_away_logo, test_h)
        home_option = _scaled(base_home_logo, test_h)
        total = at_w + spacing * 2
        total += away_option.width if away_option else _text_width(away.get("tri") or "AWY")
        total += home_option.width if home_option else _text_width(home.get("tri") or "HOME")
        if total <= max_width:
            best_layout = (test_h, spacing, away_option, home_option)
            break

    if best_layout is None:
        fallback_h = max(min_height, int(round(starting_height * 0.85)))
        spacing = max(10, int(round(fallback_h * spacing_ratio)))
        best_layout = (
            fallback_h,
            spacing,
            _scaled(base_away_logo, fallback_h),
            _scaled(base_home_logo, fallback_h),
        )

    logo_h, spacing, away_logo, home_logo = best_layout
    block_h = logo_h
    y_top = y + 2
    available_space = max(0, bottom_y - y_top)
    centered_top = y_top + max(0, (available_space - block_h) // 2)
    row_y = min(max(y_top + 1, centered_top), max(y_top + 1, bottom_y - block_h - 1))

    elements = [
        away_logo if away_logo else (away.get("tri") or "AWY"),
        at_txt,
        home_logo if home_logo else (home.get("tri") or "HOME"),
    ]
    total_w = sum(
        el.width if isinstance(el, Image.Image) else _text_width(str(el))
        for el in elements
    ) + spacing * (len(elements) - 1)
    start_x = max(0, (WIDTH - total_w) // 2)

    for el in elements:
        if isinstance(el, Image.Image):
            img.paste(el, (start_x, row_y), el)
            start_x += el.width + spacing
        else:
            w_txt = _text_width(str(el))
            h_txt = _text_h(draw, FONT_NEXT_OPP)
            ty = row_y + (block_h - h_txt) // 2
            draw.text((start_x, ty), str(el), font=FONT_NEXT_OPP, fill=TEXT_COLOR)
            start_x += w_txt + spacing

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

    footer = _format_footer_live(game)
    img = _render_scoreboard(game, title="Bulls Live:", footer=footer)
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
