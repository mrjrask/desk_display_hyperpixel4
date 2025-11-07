#!/usr/bin/env python3
"""
draw_bears_schedule.py

Shows the next Chicago Bears game with:
  - Title at y=0
  - Opponent wrapped in up to two lines, prefixed by '@' if the Bears are away,
    or 'vs.' if the Bears are home.
  - Between those and the bottom line, a row of logos: AWAY @ HOME, each logo
    auto-sized similarly to the Hawks schedule screen.
  - Bottom line with week/date/time (no spaces around the dash).
"""

import datetime
import os
from typing import Optional

from PIL import Image, ImageDraw

import config
from config import (
    BEARS_BOTTOM_MARGIN,
    BEARS_SCHEDULE,
    NFL_TEAM_ABBREVIATIONS,
    NEXT_GAME_LOGO_FONT_SIZE,
)
from utils import load_team_logo, next_game_from_schedule, wrap_text

NFL_LOGO_DIR = os.path.join(config.IMAGES_DIR, "nfl")
def show_bears_next_game(display, transition=False):
    game = next_game_from_schedule(BEARS_SCHEDULE)
    title = "Next for Da Bears:"
    img   = Image.new("RGB", (config.WIDTH, config.HEIGHT), "black")
    draw  = ImageDraw.Draw(img)

    # Title
    tw, th = draw.textsize(title, font=config.FONT_TITLE_SPORTS)
    draw.text(((config.WIDTH - tw)//2, 0), title,
              font=config.FONT_TITLE_SPORTS, fill=(255,255,255))

    if game:
        opp = game["opponent"]
        ha  = game["home_away"].lower()
        prefix = "@" if ha=="away" else "vs."

        # Opponent text (up to 2 lines)
        lines  = wrap_text(f"{prefix} {opp}", config.FONT_TEAM_SPORTS, config.WIDTH)[:2]
        y_txt  = th + 4
        for ln in lines:
            w_ln, h_ln = draw.textsize(ln, font=config.FONT_TEAM_SPORTS)
            draw.text(((config.WIDTH - w_ln)//2, y_txt),
                      ln, font=config.FONT_TEAM_SPORTS, fill=(255,255,255))
            y_txt += h_ln + 2

        # Logos row: AWAY @ HOME
        bears_ab = "chi"
        opp_key  = opp.split()[-1].lower()
        opp_ab   = NFL_TEAM_ABBREVIATIONS.get(opp_key, opp_key[:3])
        if opp_ab == "was":
            opp_ab = "wsh"
        if ha=="away":
            away_ab, home_ab, loc_sym = bears_ab, opp_ab, "@"
        else:
            away_ab, home_ab, loc_sym = opp_ab, bears_ab, "@"

        # Bottom line text — **no spaces around the dash**
        wk = game["week"]
        try:
            dt0 = datetime.datetime.strptime(game["date"], "%a, %b %d")
            date_txt = f"{dt0.month}/{dt0.day}"
        except:
            date_txt = game["date"]
        t_txt = game["time"].strip()
        bottom = f"{wk.replace('0.', 'Pre')}-{date_txt} {t_txt}"
        bw, bh = draw.textsize(bottom, font=config.FONT_DATE_SPORTS)
        bottom_y = config.HEIGHT - bh - BEARS_BOTTOM_MARGIN  # keep on-screen

        available_h = max(10, bottom_y - (y_txt + 2))
        max_logo_height = max(32, min(available_h, int(round(config.HEIGHT * 0.65))))
        base_away_logo = load_team_logo(NFL_LOGO_DIR, away_ab, height=max_logo_height)
        base_home_logo = load_team_logo(NFL_LOGO_DIR, home_ab, height=max_logo_height)

        at_txt = loc_sym
        at_w, _ = draw.textsize(at_txt, font=config.FONT_TEAM_SPORTS)
        max_width = config.WIDTH - 24
        spacing_ratio = 0.16

        def _scaled(logo: Optional[Image.Image], height: int) -> Optional[Image.Image]:
            if logo is None:
                return None
            if logo.height == height:
                return logo
            ratio = height / float(logo.height)
            return logo.resize((max(1, int(round(logo.width * ratio))), height), Image.LANCZOS)

        def _text_width(text: str) -> int:
            return draw.textsize(text, font=config.FONT_TEAM_SPORTS)[0]

        min_height = 32
        best_layout: Optional[tuple[int, int, Optional[Image.Image], Optional[Image.Image]]] = None
        starting_height = min(max_logo_height, max(min_height, available_h))
        for test_h in range(int(starting_height), min_height - 1, -2):
            spacing = max(12, int(round(test_h * spacing_ratio)))
            away_logo = _scaled(base_away_logo, test_h)
            home_logo = _scaled(base_home_logo, test_h)
            total = at_w + spacing * 2
            total += away_logo.width if away_logo else _text_width(away_ab.upper())
            total += home_logo.width if home_logo else _text_width(home_ab.upper())
            if total <= max_width:
                best_layout = (test_h, spacing, away_logo, home_logo)
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

        logo_h, spacing, logo_away, logo_home = best_layout
        block_h = logo_h
        space_top = y_txt
        space_bottom = bottom_y
        available_space = max(0, space_bottom - space_top)
        y_logo = space_top + max(0, (available_space - block_h) // 2)

        elements = []
        elements.append(logo_away if logo_away else away_ab.upper())
        elements.append(at_txt)
        elements.append(logo_home if logo_home else home_ab.upper())

        total_w = sum(
            el.width if isinstance(el, Image.Image) else _text_width(str(el))
            for el in elements
        ) + spacing * (len(elements) - 1)
        x = max(0, (config.WIDTH - total_w) // 2)

        for el in elements:
            if isinstance(el, Image.Image):
                img.paste(el, (x, y_logo), el)
                x += el.width + spacing
            else:
                w_sy, h_sy = draw.textsize(el, font=config.FONT_TEAM_SPORTS)
                y_sy = y_logo + (block_h - h_sy) // 2
                draw.text((x, y_sy), el, font=config.FONT_TEAM_SPORTS, fill=(255, 255, 255))
                x += w_sy + spacing

        # Draw bottom text
        draw.text(((config.WIDTH - bw)//2, bottom_y),
                  bottom, font=config.FONT_DATE_SPORTS, fill=(255,255,255))

    if transition:
        return img

    display.image(img)
    display.show()
    return None
