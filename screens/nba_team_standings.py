#!/usr/bin/env python3
"""NBA team standings screens tailored for the Bulls."""
import time
from typing import Iterable, Tuple

from PIL import Image, ImageDraw, ImageFont

from config import (
    WIDTH,
    HEIGHT,
    TEAM_STANDINGS_DISPLAY_SECONDS,
    FONT_STAND1_WL,
    FONT_STAND1_RANK,
    FONT_STAND1_GB_VALUE,
    FONT_STAND1_WCGB_VALUE,
    FONT_STAND2_RECORD,
    FONT_STAND2_VALUE,
    SCOREBOARD_BACKGROUND_COLOR,
)
from screens.mlb_team_standings import format_games_back
from utils import clear_display, log_call

LOGO_SZ = 180
MARGIN = 12


def _ord(n):
    try:
        i = int(n)
    except Exception:
        return f"{n}th"
    if 10 <= i % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(i % 10, "th")
    return f"{i}{suffix}"


def _load_logo(logo_path: str) -> Image.Image | None:
    try:
        logo_img = Image.open(logo_path).convert("RGBA")
        ratio = LOGO_SZ / logo_img.height
        return logo_img.resize((int(logo_img.width * ratio), LOGO_SZ), Image.ANTIALIAS)
    except Exception:
        return None


def _draw_lines(img: Image.Image, logo: Image.Image | None, lines: Iterable[Tuple[str, ImageFont.ImageFont]]):
    draw = ImageDraw.Draw(img)
    text_top = (logo.height if logo else 0) + MARGIN
    bottom_limit = HEIGHT - MARGIN

    heights = [draw.textsize(txt, font)[1] for txt, font in lines]
    total_h = sum(heights)
    spacing = (bottom_limit - text_top - total_h) / (len(heights) + 1) if lines else 0

    y = text_top + spacing
    for txt, font in lines:
        w0, h0 = draw.textsize(txt, font)
        draw.text(((WIDTH - w0) // 2, int(y)), txt, font=font, fill=(255, 255, 255))
        y += h0 + spacing


@log_call
def draw_standings_screen1(display, rec, logo_path, transition=False):
    """Screen 1: logo, W/L, rank, division GB, and conference GB."""
    if not rec:
        return None

    clear_display(display)
    img = Image.new("RGB", (WIDTH, HEIGHT), SCOREBOARD_BACKGROUND_COLOR)
    logo = _load_logo(logo_path)
    if logo:
        x0 = (WIDTH - logo.width) // 2
        img.paste(logo, (x0, 0), logo)

    lr = rec.get("leagueRecord", {}) if isinstance(rec, dict) else {}
    wins = lr.get("wins", "-")
    losses = lr.get("losses", "-")
    wl_txt = f"W: {wins} L: {losses}"

    rank = rec.get("divisionRank", "-")
    try:
        rank_lbl = "Last" if int(rank) >= 5 else _ord(rank)
    except Exception:
        rank_lbl = rank
    division_name = rec.get("divisionName", "Division")
    rank_txt = f"{rank_lbl} in {division_name}"

    gb_raw = rec.get("divisionGamesBack")
    gb_txt = f"{format_games_back(gb_raw)} GB" if gb_raw is not None else None

    conf_gb = rec.get("gamesBehind") or rec.get("gamesBack")
    conf_txt = f"{format_games_back(conf_gb)} Conf GB" if conf_gb is not None else None

    lines = [
        (wl_txt, FONT_STAND1_WL),
        (rank_txt, FONT_STAND1_RANK),
    ]
    if gb_txt:
        lines.append((gb_txt, FONT_STAND1_GB_VALUE))
    if conf_txt:
        lines.append((conf_txt, FONT_STAND1_WCGB_VALUE))

    _draw_lines(img, logo, lines)

    if transition:
        return img

    display.image(img)
    display.show()
    time.sleep(TEAM_STANDINGS_DISPLAY_SECONDS)
    return None


@log_call
def draw_standings_screen2(display, rec, logo_path, transition=False):
    """Screen 2: logo + overall record and splits."""
    if not rec:
        return None

    clear_display(display)
    img = Image.new("RGB", (WIDTH, HEIGHT), SCOREBOARD_BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    logo = _load_logo(logo_path)
    if logo:
        x0 = (WIDTH - logo.width) // 2
        img.paste(logo, (x0, 0), logo)

    lr = rec.get("leagueRecord", {}) if isinstance(rec, dict) else {}
    wins = lr.get("wins", "-")
    losses = lr.get("losses", "-")
    pct = str(lr.get("pct", "-")).lstrip("0")
    rec_txt = f"{wins}-{losses} ({pct})"

    splits = rec.get("records", {}).get("splitRecords", []) if isinstance(rec, dict) else []

    def find_split(t):
        for sp in splits:
            if sp.get("type", "").lower() == t.lower():
                return f"{sp.get('wins', '-')}-{sp.get('losses', '-')}"
        return "-"

    items = [
        f"Streak: {rec.get('streak', {}).get('streakCode', '-')}",
        f"L10: {find_split('lastTen')}",
        f"Home: {find_split('home')}",
        f"Away: {find_split('away')}",
    ]

    lines2 = [(rec_txt, FONT_STAND2_RECORD)] + [(it, FONT_STAND2_VALUE) for it in items]
    heights2 = [draw.textsize(txt, font)[1] for txt, font in lines2]
    total2 = sum(heights2)
    text_top = (logo.height if logo else 0) + MARGIN
    bottom_limit = HEIGHT - MARGIN
    spacing2 = (bottom_limit - text_top - total2) / (len(lines2) + 1)

    y = text_top + spacing2
    for txt, font in lines2:
        w0, h0 = draw.textsize(txt, font)
        draw.text(((WIDTH - w0) // 2, int(y)), txt, font=font, fill=(255, 255, 255))
        y += h0 + spacing2

    if transition:
        return img

    display.image(img)
    display.show()
    time.sleep(TEAM_STANDINGS_DISPLAY_SECONDS)
    return None
