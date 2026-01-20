#!/usr/bin/env python3
"""
draw_bears_schedule.py

Shows the next Chicago Bears game with:
  - Title at y=0
  - Opponent wrapped in up to two lines, prefixed by '@' if the Bears are away,
    or 'vs.' if the Bears are home.
  - Between those and the bottom line, a row of logos: AWAY @ HOME, each logo
    auto-sized similarly to the Hawks schedule screen.
  - Footer with optional event name above the date/time.
"""

import os
import re
import time
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

import config
from config import (
    BEARS_BOTTOM_MARGIN,
    BEARS_SCHEDULE,
    NFL_TEAM_ABBREVIATIONS,
)
from utils import (
    load_team_logo,
    next_game_from_schedule,
    square_logo_frame,
    wrap_text,
)

NFL_LOGO_DIR = os.path.join(config.IMAGES_DIR, "nfl")

DROP_MARGIN = 24
DROP_STEPS = 24
DROP_STAGGER = 0.4
DROP_FRAME_DELAY = 0.02


def _ease_out_cubic(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    inv = 1.0 - t
    return 1.0 - inv * inv * inv


def _text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> tuple[int, int]:
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l, b - t
    except Exception:  # pragma: no cover - PIL fallback
        return draw.textsize(text, font=font)


def show_bears_next_game(display, transition=False):
    game = next_game_from_schedule(BEARS_SCHEDULE)
    title = "Next for Da Bears:"
    img   = Image.new("RGB", (config.WIDTH, config.HEIGHT), "black")
    draw  = ImageDraw.Draw(img)

    if game:
        def _format_date_time_line(game_data: dict) -> str:
            date_text = game_data.get("date", "").strip()
            time_text = game_data.get("time", "").strip()
            date_text = re.sub(r"\b\d{4}\b", "", date_text).strip()
            date_text = " ".join(date_text.split())
            return f"{date_text} {time_text}".strip()

        title_w, title_h = draw.textsize(title, font=config.FONT_TITLE_SPORTS)
        draw.text(((config.WIDTH - title_w)//2, 0), title,
                  font=config.FONT_TITLE_SPORTS, fill=(255,255,255))

        opp = game["opponent"]
        ha  = game["home_away"].lower()
        prefix = "@" if ha=="away" else "vs."

        # Opponent text (up to 2 lines)
        lines  = wrap_text(f"{prefix} {opp}", config.FONT_TEAM_SPORTS, config.WIDTH)[:2]
        y_txt  = title_h + 6
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

        # Bottom dateline text — event name above week above date/time
        name_line = game.get("name", "").strip()
        if name_line == title:
            name_line = ""
        week_line = game.get("week", "").strip()
        date_time_line = _format_date_time_line(game)
        if name_line:
            name_w, name_h = draw.textsize(name_line, font=config.FONT_DATE_SPORTS)
        else:
            name_w, name_h = 0, 0
        if week_line:
            week_w, week_h = draw.textsize(week_line, font=config.FONT_DATE_SPORTS)
        else:
            week_w, week_h = 0, 0
        date_w, date_h = draw.textsize(date_time_line, font=config.FONT_DATE_SPORTS)
        date_y = config.HEIGHT - date_h - BEARS_BOTTOM_MARGIN  # keep on-screen
        week_y = date_y - week_h - 2 if week_line else date_y
        name_y = week_y - name_h - 2 if name_line else week_y

        horizontal_padding = max(12, int(round(config.WIDTH * 0.02)))
        vertical_padding = max(4, int(round(config.HEIGHT * 0.01)))
        min_spacing = max(10, int(round(config.WIDTH * 0.015)))

        logo_area_top = y_txt + vertical_padding
        bottom_text_top = name_y if name_line else week_y if week_line else date_y
        logo_area_bottom = bottom_text_top - vertical_padding
        available_h = max(10, logo_area_bottom - logo_area_top)
        max_logo_height = max(36, available_h)
        frame_ceiling = max_logo_height

        base_away_logo = load_team_logo(NFL_LOGO_DIR, away_ab, height=max_logo_height)
        base_home_logo = load_team_logo(NFL_LOGO_DIR, home_ab, height=max_logo_height)

        at_txt = loc_sym
        at_w, _ = draw.textsize(at_txt, font=config.FONT_TEAM_SPORTS)
        max_width = config.WIDTH - (horizontal_padding * 2)
        spacing_ratio = 0.16

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
                    square_logo_frame(
                        base_away_logo,
                        test_h,
                        fallback_text=away_ab.upper(),
                        fallback_font=config.FONT_TEAM_SPORTS,
                    ),
                    square_logo_frame(
                        base_home_logo,
                        test_h,
                        fallback_text=home_ab.upper(),
                        fallback_font=config.FONT_TEAM_SPORTS,
                    ),
                )
                break

        if best_layout is None:
            fallback_h = max(min_height, int(round(starting_height * 0.85)))
            spacing = max(min_spacing, int(round(fallback_h * spacing_ratio)))
            best_layout = (
                fallback_h,
                spacing,
                square_logo_frame(
                    base_away_logo,
                    fallback_h,
                    fallback_text=away_ab.upper(),
                    fallback_font=config.FONT_TEAM_SPORTS,
                ),
                square_logo_frame(
                    base_home_logo,
                    fallback_h,
                    fallback_text=home_ab.upper(),
                    fallback_font=config.FONT_TEAM_SPORTS,
                ),
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
        if name_line:
            draw.text(
                ((config.WIDTH - name_w) // 2, name_y),
                name_line,
                font=config.FONT_DATE_SPORTS,
                fill=(255, 255, 255),
            )
        if week_line:
            draw.text(
                ((config.WIDTH - week_w) // 2, week_y),
                week_line,
                font=config.FONT_DATE_SPORTS,
                fill=(255, 255, 255),
            )
        draw.text(
            ((config.WIDTH - date_w) // 2, date_y),
            date_time_line,
            font=config.FONT_DATE_SPORTS,
            fill=(255, 255, 255),
        )
    else:
        tw, th = draw.textsize(title, font=config.FONT_TITLE_SPORTS)
        draw.text(((config.WIDTH - tw)//2, 0), title,
                  font=config.FONT_TITLE_SPORTS, fill=(255,255,255))

    if transition:
        return img

    display.image(img)
    display.show()
    return None


def _render_drop_frames(
    display,
    header: Image.Image,
    placements: list[dict],
    *,
    transition: bool,
) -> Image.Image:
    if not placements:
        if transition:
            return header
        display.image(header)
        display.show()
        return header

    steps = max(2, DROP_STEPS)
    stagger = max(1, int(round(steps * DROP_STAGGER)))
    schedule: list[tuple[int, dict]] = []
    start_step = 0
    for placement in placements:
        schedule.append((start_step, placement))
        start_step += stagger

    total_duration = schedule[-1][0] + steps + 1
    placed: list[dict] = []
    completed = [False] * len(schedule)

    for current_step in range(total_duration):
        for idx, (start, placement) in enumerate(schedule):
            if current_step >= start + steps and not completed[idx]:
                placed.append(
                    {
                        "logo": placement["logo"],
                        "x": placement["x"],
                        "y": placement["y"],
                    }
                )
                completed[idx] = True

        frame = header.copy()
        for placement in placed:
            frame.paste(placement["logo"], (placement["x"], placement["y"]), placement["logo"])

        for start, placement in schedule:
            progress = current_step - start
            if progress < 0 or progress >= steps:
                continue

            frac = progress / (steps - 1) if steps > 1 else 1.0
            eased = _ease_out_cubic(frac)
            start_y = placement["drop_start"]
            target_y = placement["y"]
            y_pos = int(start_y + (target_y - start_y) * eased)
            if y_pos > target_y:
                y_pos = target_y
            frame.paste(placement["logo"], (placement["x"], y_pos), placement["logo"])

        display.image(frame)
        display.show()
        time.sleep(DROP_FRAME_DELAY)

    final = header.copy()
    for placement in placements:
        final.paste(placement["logo"], (placement["x"], placement["y"]), placement["logo"])
    display.image(final)
    display.show()
    return final


def show_bears_next_season(display, transition=False):
    title = "2026 Bears Opponents"
    img = Image.new("RGB", (config.WIDTH, config.HEIGHT), "black")
    draw = ImageDraw.Draw(img)

    title_w, title_h = _text_size(draw, title, config.FONT_TITLE_SPORTS)
    draw.text(
        ((config.WIDTH - title_w) // 2, 0),
        title,
        font=config.FONT_TITLE_SPORTS,
        fill=(255, 255, 255),
    )

    header_gap = max(8, int(round(config.HEIGHT * 0.02)))
    heading_y = title_h + header_gap
    heading_font = config.FONT_TEAM_SPORTS
    heading_spacing = max(6, int(round(config.WIDTH * 0.02)))

    home_heading = "Home"
    away_heading = "Away"
    home_w, home_h = _text_size(draw, home_heading, heading_font)
    away_w, away_h = _text_size(draw, away_heading, heading_font)

    content_top = heading_y + max(home_h, away_h) + header_gap
    content_bottom = config.HEIGHT - max(8, int(round(config.HEIGHT * 0.03)))
    content_height = max(10, content_bottom - content_top)

    half_width = config.WIDTH // 2
    side_padding = max(12, int(round(config.WIDTH * 0.03)))
    section_width = half_width - side_padding * 2

    home_center = half_width // 2
    away_center = half_width + home_center

    draw.text(
        (home_center - home_w // 2, heading_y),
        home_heading,
        font=heading_font,
        fill=(255, 255, 255),
    )
    draw.text(
        (away_center - away_w // 2, heading_y),
        away_heading,
        font=heading_font,
        fill=(255, 255, 255),
    )

    home_teams = ["DET", "GB", "MIN", "TB", "PHI", "JAX", "NYJ", "NE", "NO"]
    away_teams = ["DET", "GB", "MIN", "BUF", "MIA", "ATL", "CAR", "SEA"]

    cols = 2
    rows = max(
        (len(home_teams) + cols - 1) // cols,
        (len(away_teams) + cols - 1) // cols,
    )
    col_gap = max(6, int(round(section_width * 0.08)))
    row_gap = max(6, int(round(content_height * 0.06)))

    cell_width = max(
        12,
        int(round((section_width - col_gap * (cols - 1)) / cols)),
    )
    cell_height = max(
        12,
        int(round((content_height - row_gap * (rows - 1)) / rows)),
    )
    logo_size = max(20, min(cell_width, cell_height))

    def _placements_for(
        teams: list[str],
        center_x: int,
    ) -> list[dict]:
        grid_width = logo_size * cols + col_gap * (cols - 1)
        grid_height = logo_size * rows + row_gap * (rows - 1)
        start_x = center_x - grid_width // 2
        start_y = content_top + max(0, (content_height - grid_height) // 2)
        placements: list[dict] = []

        for idx, abbr in enumerate(teams):
            row = idx // cols
            col = idx % cols
            if row >= rows:
                break
            base_logo = load_team_logo(NFL_LOGO_DIR, abbr.lower(), height=logo_size)
            framed = square_logo_frame(
                base_logo,
                logo_size,
                fallback_text=abbr,
                fallback_font=config.FONT_TEAM_SPORTS,
            )
            if not framed:
                continue
            x = start_x + col * (logo_size + col_gap)
            y = start_y + row * (logo_size + row_gap)
            drop_start = min(-logo_size, content_top - logo_size - DROP_MARGIN)
            placements.append(
                {
                    "logo": framed,
                    "x": x,
                    "y": y,
                    "drop_start": drop_start,
                }
            )
        return placements

    placements = _placements_for(home_teams, home_center) + _placements_for(
        away_teams, away_center
    )

    if transition:
        final = img.copy()
        for placement in placements:
            final.paste(
                placement["logo"],
                (placement["x"], placement["y"]),
                placement["logo"],
            )
        return final

    _render_drop_frames(display, img, placements, transition=False)
    return None
