#!/usr/bin/env python3
"""
draw_bears_schedule.py

Shows the next Chicago Bears game with:
  - Title at y=0
  - Opponent wrapped in up to two lines, prefixed by '@' if the Bears are away,
    or 'vs.' if the Bears are home.
  - Between those and the bottom line, a row of logos: AWAY @ HOME, each logo
    auto-sized similarly to the Hawks schedule screen.
  - Two-line footer with event name above the date/time.
"""

import os
from typing import Optional

from PIL import Image, ImageDraw

import config
from config import (
    BEARS_BOTTOM_MARGIN,
    BEARS_SCHEDULE,
    NFL_TEAM_ABBREVIATIONS,
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
        opp_key = opp.split()[-1].lower()
        if opp_key == "tbd":
            opp_ab = "AFC" if "super bowl" in game.get("week", "").lower() else "NFC"
        else:
            opp_ab = NFL_TEAM_ABBREVIATIONS.get(opp_key, opp_key[:3])
        if opp_ab == "was":
            opp_ab = "wsh"
        if ha=="away":
            away_ab, home_ab, loc_sym = bears_ab, opp_ab, "@"
        else:
            away_ab, home_ab, loc_sym = opp_ab, bears_ab, "@"

        # Bottom dateline text — event name above date/time
        name_line = game.get("name", title)
        date_time_line = f"{game.get('date', '').strip()} {game.get('time', '').strip()}".strip()
        name_w, name_h = draw.textsize(name_line, font=config.FONT_DATE_SPORTS)
        date_w, date_h = draw.textsize(date_time_line, font=config.FONT_DATE_SPORTS)
        date_y = config.HEIGHT - date_h - BEARS_BOTTOM_MARGIN  # keep on-screen
        name_y = date_y - name_h - 2

        horizontal_padding = max(12, int(round(config.WIDTH * 0.02)))
        vertical_padding = max(4, int(round(config.HEIGHT * 0.01)))
        min_spacing = max(10, int(round(config.WIDTH * 0.015)))

        logo_area_top = y_txt + vertical_padding
        logo_area_bottom = name_y - vertical_padding
        available_h = max(10, logo_area_bottom - logo_area_top)
        max_logo_height = max(36, min(available_h, int(round(config.HEIGHT * 0.6))))
        frame_ceiling = max_logo_height

        base_away_logo = load_team_logo(NFL_LOGO_DIR, away_ab, height=max_logo_height)
        base_home_logo = load_team_logo(NFL_LOGO_DIR, home_ab, height=max_logo_height)

        at_txt = loc_sym
        at_w, _ = draw.textsize(at_txt, font=config.FONT_TEAM_SPORTS)
        max_width = config.WIDTH - (horizontal_padding * 2)
        spacing_ratio = 0.16

        def _logo_frame(logo: Optional[Image.Image], fallback: str, size: int) -> Optional[Image.Image]:
            if size <= 0:
                return None

            frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            if logo is not None:
                ratio = 1.0
                try:
                    ratio = min(size / float(logo.height or 1), size / float(logo.width or 1))
                except Exception:
                    ratio = 1.0
                if ratio and abs(ratio - 1.0) > 1e-3:
                    logo = logo.resize(
                        (
                            max(1, int(round(logo.width * ratio))),
                            max(1, int(round(logo.height * ratio))),
                        ),
                        Image.LANCZOS,
                    )
                x_off = (size - logo.width) // 2
                y_off = (size - logo.height) // 2
                frame.paste(logo, (x_off, y_off), logo)
                return frame

            if fallback:
                drawer = ImageDraw.Draw(frame)
                tw = drawer.textsize(fallback, font=config.FONT_TEAM_SPORTS)[0]
                th = drawer.textsize(fallback, font=config.FONT_TEAM_SPORTS)[1]
                drawer.text(
                    ((size - tw) // 2, (size - th) // 2),
                    fallback,
                    font=config.FONT_TEAM_SPORTS,
                    fill=(255, 255, 255),
                )
            return frame

        def _text_width(text: str) -> int:
            return draw.textsize(text, font=config.FONT_TEAM_SPORTS)[0]

        min_height = 32
        best_layout: Optional[tuple[int, int, Optional[Image.Image], Optional[Image.Image]]] = None
        starting_height = max(
            min_height,
            min(frame_ceiling if frame_ceiling > 0 else max_logo_height, available_h),
        )
        for test_h in range(int(starting_height), min_height - 1, -2):
            spacing = max(min_spacing, int(round(test_h * spacing_ratio)))
            total = at_w + spacing * 2 + test_h * 2
            if total <= max_width:
                best_layout = (
                    test_h,
                    spacing,
                    _logo_frame(base_away_logo, away_ab.upper(), test_h),
                    _logo_frame(base_home_logo, home_ab.upper(), test_h),
                )
                break

        if best_layout is None:
            fallback_h = max(min_height, int(round(starting_height * 0.85)))
            spacing = max(min_spacing, int(round(fallback_h * spacing_ratio)))
            best_layout = (
                fallback_h,
                spacing,
                _logo_frame(base_away_logo, away_ab.upper(), fallback_h),
                _logo_frame(base_home_logo, home_ab.upper(), fallback_h),
            )

        logo_h, spacing, logo_away, logo_home = best_layout
        block_h = logo_h
        available_space = max(0, logo_area_bottom - logo_area_top)
        centered_top = logo_area_top + max(0, (available_space - block_h) // 2)
        y_logo = min(
            max(logo_area_top, centered_top),
            max(logo_area_top, logo_area_bottom - block_h),
        )

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
        draw.text(((config.WIDTH - name_w)//2, name_y),
                  name_line, font=config.FONT_DATE_SPORTS, fill=(255,255,255))
        draw.text(((config.WIDTH - date_w)//2, date_y),
                  date_time_line, font=config.FONT_DATE_SPORTS, fill=(255,255,255))

    if transition:
        return img

    display.image(img)
    display.show()
    return None
