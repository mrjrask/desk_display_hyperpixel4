#!/usr/bin/env python3
"""
mlb_team_standings.py

Draw MLB team standings screens 1 & 2 in RGB.
Screen 1: logo at top center, then W-L, rank, GB, WCGB with:
  - “--” for 0 WCGB
  - “+n” for any of the top-3 wild card slots when WCGB > 0
  - “n” for everyone else
Screen 2: logo at top center, then overall record and splits.
"""
import os
import time
from typing import Any, Mapping, Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

from config import (
    WIDTH,
    HEIGHT,
    TEAM_STANDINGS_DISPLAY_SECONDS,
    FONT_STAND1_WL,
    FONT_STAND1_RANK,
    FONT_STAND1_GB_LABEL,
    FONT_STAND1_GB_VALUE,
    FONT_STAND1_WCGB_LABEL,
    FONT_STAND1_WCGB_VALUE,
    FONT_STAND2_RECORD,
    FONT_STAND2_VALUE,
    SCOREBOARD_BACKGROUND_COLOR,
)
from utils import clear_display, log_call

# Constants tuned per display profile
LOGO_SZ = max(40, int(min(WIDTH, HEIGHT) * 0.25))
MARGIN = max(4, int(min(WIDTH, HEIGHT) * 0.015))

# Helpers
def _ord(n: Any) -> str:
    try:
        i = int(n)
    except Exception:
        return f"{n}th"
    if 10 <= i % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(i % 10, "th")
    return f"{i}{suffix}"


def _format_int(value: Any) -> str:
    try:
        number = int(value)
    except Exception:
        return "-"
    return f"{number:d}"


def _format_streak(raw_value: Any) -> str:
    if not raw_value:
        return "-"
    if isinstance(raw_value, str):
        return raw_value
    try:
        streak = int(raw_value)
    except Exception:
        return str(raw_value)
    prefix = "W" if streak >= 0 else "L"
    return f"{prefix}{abs(streak)}"


def _format_pct_value(pct_raw: Any, *, precision: int) -> str:
    try:
        pct_val = float(pct_raw)
        pct_txt = f"{pct_val:.{precision}f}"
    except Exception:
        return str(pct_raw).lstrip("0")

    if pct_txt.startswith("-0"):
        pct_txt = f"-{pct_txt[2:]}"
    elif pct_txt.startswith("0"):
        pct_txt = pct_txt[1:]
    return pct_txt


def _format_record_values(record: Mapping[str, Any], *, ot_label: str = "OT") -> str:
    wins = record.get("wins", "-")
    losses = record.get("losses", "-")
    ties = record.get("ties") if record.get("ties") not in (0, "0") else None
    if ties in (None, "", "-", 0, "0"):
        ties = record.get("ot") if record.get("ot") not in (0, "0") else None
    base = f"{wins}-{losses}"
    if ties not in (None, "", "-", 0, "0"):
        base = f"{base}-{ties}"
    ot = record.get("ot", 0)
    ot_txt = f" ({ot_label} {ot})" if ot not in (None, "", "-", 0, "0") else ""
    return f"{base}{ot_txt}"


def _scaled_font(font: ImageFont.ImageFont, scale: float | None) -> ImageFont.ImageFont:
    """Return ``font`` scaled by ``scale`` when possible."""

    if scale in (None, 1):
        return font

    try:
        base_size = getattr(font, "size", None)
        path = getattr(font, "path", None)
        if not base_size or not path or scale is None or scale <= 0:
            return font

        scaled_size = max(1, int(round(base_size * scale)))
        if scaled_size == base_size:
            return font

        return ImageFont.truetype(path, scaled_size)
    except Exception:
        return font


def format_games_back(gb: Any) -> str:
    """
    Convert raw games-back (float) into display string:
     - integer -> "5"
     - half games -> "½" or "3½"
    """
    try:
        v = float(gb)
        v_abs = abs(v)
        if v_abs.is_integer():
            return f"{int(v_abs)}"
        if abs(v_abs - int(v_abs) - 0.5) < 1e-3:
            return f"{int(v_abs)}½" if int(v_abs) > 0 else "½"
    except Exception:
        pass
    return str(gb)


@log_call
def draw_standings_screen1(
    display,
    rec: Mapping[str, Any] | None,
    logo_path: str,
    division_name: str,
    *,
    rank_font: ImageFont.ImageFont | None = None,
    wl_font: ImageFont.ImageFont | None = None,
    wl_font_scale: float | None = None,
    show_games_back: bool = True,
    show_wild_card: bool = True,
    gb_label: str | None = "GB",
    wild_card_label: str | None = "WCGB",
    show_streak: bool = False,
    ot_label: str = "OT",
    points_label: str | None = None,
    points_font: ImageFont.ImageFont | None = None,
    conference_label: str | None = None,
    show_conference_rank: bool = True,
    place_gb_before_rank: bool = False,
    show_pct: bool = False,
    pct_precision: int | None = None,
    record_details_fn=None,
    last_place_rank: int | None = 5,
    transition: bool = False,
):
    """
    Screen 1: logo, W/L, rank, optional GB/WCGB.
    """
    if not rec:
        return None

    clear_display(display)
    img = Image.new("RGB", (WIDTH, HEIGHT), SCOREBOARD_BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    # Logo
    logo = None
    try:
        logo_img = Image.open(logo_path).convert("RGBA")
        ratio = min(LOGO_SZ / logo_img.width, LOGO_SZ / logo_img.height)
        logo = logo_img.resize(
            (
                max(1, int(round(logo_img.width * ratio))),
                max(1, int(round(logo_img.height * ratio))),
            ),
            Image.ANTIALIAS,
        )
    except Exception:
        pass
    if logo:
        x0 = (WIDTH - logo.width) // 2
        y0 = (LOGO_SZ - logo.height) // 2
        img.paste(logo, (x0, max(0, y0)), logo)

    text_top = LOGO_SZ + MARGIN
    bottom_limit = HEIGHT - MARGIN

    # W/L
    record_line = _format_record_values(rec.get("leagueRecord", {}), ot_label=ot_label)

    if record_details_fn:
        wl_txt = record_details_fn(rec, record_line)
    elif show_pct:
        pct_raw = rec.get("leagueRecord", {}).get("pct", "-")
        precision = 3 if pct_precision is None else pct_precision
        pct_txt = _format_pct_value(pct_raw, precision=precision)
        wl_txt = f"{record_line} ({pct_txt})"
    else:
        wl_txt = record_line

    points_txt = None
    if points_label is not None:
        pts_val = _format_int(rec.get("points"))
        points_txt = f"{pts_val} {points_label}"

    # Division rank
    rank_font = rank_font or FONT_STAND1_RANK
    dr = rec.get("divisionRank", "-")
    try:
        dr_int = int(dr)
        if last_place_rank is not None and dr_int == last_place_rank:
            dr_lbl = "Last"
        else:
            dr_lbl = _ord(dr_int)
    except Exception:
        dr_lbl = dr
    rank_txt = f"{dr_lbl} in {division_name}"

    # GB
    gb_txt = None
    if show_games_back:
        gb_raw = rec.get("divisionGamesBack", "-")
        gb_label_txt = f" {gb_label}" if gb_label else ""
        gb_txt = (
            f"{format_games_back(gb_raw)}{gb_label_txt}"
            if gb_raw != "-"
            else f"-{gb_label_txt}"
        )

    # WCGB
    wc_txt = None
    if show_wild_card:
        wc_raw = rec.get("wildCardGamesBack")
        wc_rank = rec.get("wildCardRank")
        if wc_raw is not None:
            base = format_games_back(wc_raw)
            wc_label_txt = f" {wild_card_label}" if wild_card_label else ""
            try:
                rank_int = int(wc_rank)
            except Exception:
                rank_int = None

            if wc_raw == 0:
                wc_txt = f"--{wc_label_txt}"
            elif rank_int and rank_int <= 3:
                wc_txt = f"+{base}{wc_label_txt}"
            else:
                wc_txt = f"{base}{wc_label_txt}"

    # Lines to draw
    wl_font = wl_font or _scaled_font(FONT_STAND1_WL, wl_font_scale)
    lines: list[tuple[str, Any]] = [
        (wl_txt, wl_font),
    ]
    if points_txt:
        lines.append((points_txt, points_font or FONT_STAND1_GB_VALUE))
    if gb_txt and place_gb_before_rank:
        lines.append((gb_txt, FONT_STAND1_GB_VALUE))
    lines.append((rank_txt, rank_font))
    if conference_label and show_conference_rank:
        conf_rank = rec.get("conferenceRank", "-")
        try:
            conf_lbl = "Last" if int(conf_rank) == 16 else _ord(conf_rank)
        except Exception:
            conf_lbl = conf_rank
        conf_name = rec.get("conferenceName") or rec.get("conferenceAbbrev") or "conference"
        lines.append((f"{conf_lbl} in {conf_name}", rank_font))
    if gb_txt and not place_gb_before_rank:
        lines.append((gb_txt, FONT_STAND1_GB_VALUE))
    if wc_txt:
        lines.append((wc_txt, FONT_STAND1_WCGB_VALUE))
    if show_streak:
        streak_raw = (rec.get("streak") or {}).get("streakCode", "-")
        lines.append((f"Streak: {_format_streak(streak_raw)}", rank_font))

    # Layout text
    heights = [draw.textsize(txt, font)[1] for txt, font in lines]
    total_h = sum(heights)
    avail_h = bottom_limit - text_top
    spacing = (avail_h - total_h) / (len(lines) + 1) if lines else 0

    y = text_top + spacing
    for txt, font in lines:
        w0, h0 = draw.textsize(txt, font)
        draw.text(((WIDTH - w0) // 2, int(y)), txt, font=font, fill=(255, 255, 255))
        y += h0 + spacing

    if transition:
        return img

    display.image(img)
    display.show()
    time.sleep(TEAM_STANDINGS_DISPLAY_SECONDS)
    return None


@log_call
def draw_standings_screen2(
    display,
    rec: Mapping[str, Any] | None,
    logo_path: str,
    *,
    pct_precision: int | None = None,
    record_details_fn=None,
    split_order: Sequence[str] = ("lastTen", "home", "away"),
    split_overrides: Mapping[str, str] | None = None,
    show_streak: bool = True,
    show_points: bool = True,
    transition: bool = False,
):
    """
    Screen 2: logo + overall record and splits.
    """
    if not rec:
        return None

    clear_display(display)
    img = Image.new("RGB", (WIDTH, HEIGHT), SCOREBOARD_BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    # Logo
    logo = None
    try:
        logo_img = Image.open(logo_path).convert("RGBA")
        ratio = min(LOGO_SZ / logo_img.width, LOGO_SZ / logo_img.height)
        logo = logo_img.resize(
            (
                max(1, int(round(logo_img.width * ratio))),
                max(1, int(round(logo_img.height * ratio))),
            ),
            Image.ANTIALIAS,
        )
    except Exception:
        pass
    if logo:
        x0 = (WIDTH - LOGO_SZ) // 2 + (LOGO_SZ - logo.width) // 2
        y0 = (LOGO_SZ - logo.height) // 2
        img.paste(logo, (x0, max(0, y0)), logo)

    text_top = LOGO_SZ + MARGIN
    bottom_limit = HEIGHT - MARGIN

    # Overall record
    record = rec.get("leagueRecord", {})
    w = record.get("wins", "-")
    l = record.get("losses", "-")
    t = record.get("ties") if record.get("ties") not in (0, "0") else None
    if t in (None, "", "-", 0, "0"):
        t = record.get("ot") if record.get("ot") not in (0, "0") else None
    pct_raw = record.get("pct", "-")
    precision = 3 if pct_precision is None else pct_precision
    pct = _format_pct_value(pct_raw, precision=precision)

    base_rec = f"{w}-{l}"
    if t not in (None, "", "-", 0, "0"):
        base_rec = f"{base_rec}-{t}"
    if record_details_fn:
        rec_txt = record_details_fn(rec, base_rec)
    else:
        rec_txt = f"{base_rec} ({pct})"

    # Splits
    split_overrides = split_overrides or {}
    splits = rec.get("records", {}).get("splitRecords", [])

    def find_split(t_split: str) -> str:
        if t_split in split_overrides:
            return split_overrides[t_split]
        for sp in splits:
            if sp.get("type", "").lower() == t_split.lower():
                return f"{sp.get('wins', '-')}-{sp.get('losses', '-')}"
        return "-"

    items: list[str] = []
    if show_streak:
        streak_raw = rec.get("streak", {}).get("streakCode", "-")
        items.append(f"Streak: {_format_streak(streak_raw)}")
    pts = rec.get("points")
    if show_points and pts not in (None, ""):
        items.append(f"Pts: {_format_int(pts)}")
    for split in split_order:
        label = {
            "lastTen": "L10",
            "home": "Home",
            "away": "Away",
            "division": "Division",
            "conference": "Conference",
        }.get(split, split)
        items.append(f"{label}: {find_split(split)}")

    lines2 = [(rec_txt, FONT_STAND2_RECORD)] + [(it, FONT_STAND2_VALUE) for it in items]
    heights2 = [draw.textsize(txt, font)[1] for txt, font in lines2]
    total2 = sum(heights2)
    avail2 = bottom_limit - text_top
    spacing2 = (avail2 - total2) / (len(lines2) + 1) if lines2 else 0

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


__all__ = [
    "draw_standings_screen1",
    "draw_standings_screen2",
    "format_games_back",
    "_format_int",
]
