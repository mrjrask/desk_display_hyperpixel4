#!/usr/bin/env python3
"""Shared stacked-logo layout utilities for Scoreboard v3 screens."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from PIL import Image, ImageDraw

from config import HEIGHT, WIDTH
from utils import ScreenImage, clear_display


@dataclass
class ScoreboardV3Adapter:
    """Adapter describing how to fetch and draw a league's scoreboard."""

    title: str
    base_module: Any
    fetch_games: Callable[[], list[dict]]
    extract_teams: Callable[[dict], Tuple[dict, dict]]
    team_accessor: Callable[[dict], dict]
    possession_lookup: Optional[Callable[[dict], dict]] = None
    no_games_message: str = "No games"
    padding_x: int = 18
    padding_top: int = 12
    padding_bottom: int = 16
    time_text_height: int = 34
    row_gap: int = 12
    logo_column_width: int = 150
    score_gap: int = 18
    logo_margin: int = 6
    team_row_height: Optional[int] = None

    def __post_init__(self) -> None:
        base = self.base_module
        if self.team_row_height is None:
            self.team_row_height = max(90, getattr(base, "LOGO_HEIGHT", 110) + 10)

        # Ensure the logo column fits within the game width.
        game_width = getattr(base, "GAME_WIDTH", WIDTH)
        max_logo_width = max(60, game_width - 2 * self.padding_x - 90)
        self.logo_column_width = min(self.logo_column_width, max_logo_width)

    @property
    def game_height(self) -> int:
        return (
            self.padding_top
            + self.time_text_height
            + self.team_row_height * 2
            + self.row_gap
            + self.padding_bottom
        )


def _left_align_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    fill=(255, 255, 255),
):
    if not text:
        return
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = r - l, b - t
        tx = x - l
        ty = y + (height - th) // 2 - t
    except Exception:
        tw, th = draw.textsize(text, font=font)
        tx = x
        ty = y + (height - th) // 2
    draw.text((tx, ty), text, font=font, fill=fill)


def _draw_team_row(
    adapter: ScoreboardV3Adapter,
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    team_side: dict,
    score_text: str,
    score_fill: Tuple[int, int, int],
    x_offset: int,
    top: int,
    possession: bool,
):
    base = adapter.base_module
    row_left = x_offset + adapter.padding_x
    logo_left = row_left
    logo_width = adapter.logo_column_width
    score_left = logo_left + logo_width + adapter.score_gap
    game_width = getattr(base, "GAME_WIDTH", WIDTH)
    score_width = max(60, game_width - (score_left - x_offset) - adapter.padding_x)

    team_obj = adapter.team_accessor(team_side)
    logo = None
    abbr = None
    if hasattr(base, "_team_logo_abbr"):
        abbr = base._team_logo_abbr(team_obj)
    if abbr and hasattr(base, "_load_logo_cached"):
        logo = base._load_logo_cached(abbr)
    if logo and hasattr(base, "_fit_logo_to_width"):
        max_width = max(10, logo_width - adapter.logo_margin * 2)
        fitted = base._fit_logo_to_width(logo, max_width)
        if fitted:
            x0 = logo_left + (logo_width - fitted.width) // 2
            y0 = top + (adapter.team_row_height - fitted.height) // 2
            canvas.paste(fitted, (x0, y0), fitted)

    _left_align_text(
        draw,
        score_text,
        base.SCORE_FONT,
        score_left,
        top,
        score_width,
        adapter.team_row_height,
        fill=score_fill,
    )

    if not possession:
        return
    get_icon = getattr(base, "_get_possession_icon", None)
    if not get_icon:
        return
    icon = get_icon()
    if not icon:
        return
    icon_x = score_left + score_width - icon.width
    icon_y = top + (adapter.team_row_height - icon.height) // 2
    canvas.paste(icon, (icon_x, icon_y), icon)


def _draw_game_block(
    adapter: ScoreboardV3Adapter,
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    game: dict,
    x_offset: int,
    y_offset: int,
):
    base = adapter.base_module
    away, home = adapter.extract_teams(game)
    show_scores = base._should_display_scores(game)
    away_text = base._score_text(away, show=show_scores)
    home_text = base._score_text(home, show=show_scores)
    in_progress = base._is_game_in_progress(game)
    final = base._is_game_final(game)
    results = base._final_results(away, home) if final else {"away": None, "home": None}
    possession_flags = (
        adapter.possession_lookup(game)
        if adapter.possession_lookup
        else {"away": False, "home": False}
    )

    row_left = x_offset + adapter.padding_x
    row_width = getattr(base, "GAME_WIDTH", WIDTH) - 2 * adapter.padding_x
    status_fill = (
        base.IN_PROGRESS_STATUS_COLOR
        if in_progress
        else (255, 255, 255)
    )
    status_top = y_offset + adapter.padding_top
    _left_align_text(
        draw,
        base._format_status(game),
        base.STATUS_FONT,
        row_left,
        status_top,
        row_width,
        adapter.time_text_height,
        fill=status_fill,
    )

    away_top = status_top + adapter.time_text_height
    home_top = away_top + adapter.team_row_height + adapter.row_gap

    _draw_team_row(
        adapter,
        canvas,
        draw,
        team_side=away,
        score_text=away_text,
        score_fill=base._score_fill(
            "away", in_progress=in_progress, final=final, results=results
        ),
        x_offset=x_offset,
        top=away_top,
        possession=bool(possession_flags.get("away")),
    )

    _draw_team_row(
        adapter,
        canvas,
        draw,
        team_side=home,
        score_text=home_text,
        score_fill=base._score_fill(
            "home", in_progress=in_progress, final=final, results=results
        ),
        x_offset=x_offset,
        top=home_top,
        possession=bool(possession_flags.get("home")),
    )


def _compose_canvas(adapter: ScoreboardV3Adapter, games: list[dict]) -> Image.Image:
    base = adapter.base_module
    if not games:
        return Image.new("RGB", (WIDTH, HEIGHT), base.BACKGROUND_COLOR)

    game_width = getattr(base, "GAME_WIDTH", WIDTH)
    games_per_row = getattr(base, "GAMES_PER_ROW", 1)
    block_spacing = getattr(base, "BLOCK_SPACING", 0)

    num_rows = (len(games) + games_per_row - 1) // games_per_row
    total_height = adapter.game_height * num_rows
    if num_rows > 1:
        total_height += block_spacing * (num_rows - 1)

    canvas = Image.new("RGB", (WIDTH, total_height), base.BACKGROUND_COLOR)
    draw = ImageDraw.Draw(canvas)

    for idx, game in enumerate(games):
        row = idx // games_per_row
        col = idx % games_per_row
        x_offset = col * game_width
        y_offset = row * (adapter.game_height + block_spacing)
        _draw_game_block(adapter, canvas, draw, game, x_offset, y_offset)

        # Vertical separator
        if col == 0 and idx < len(games) - 1 and games_per_row > 1:
            sep_x = game_width
            sep_y_start = y_offset + adapter.padding_top
            sep_y_end = y_offset + adapter.game_height - adapter.padding_bottom
            draw.line((sep_x, sep_y_start, sep_x, sep_y_end), fill=(60, 60, 60), width=2)

        # Horizontal separator between rows
        if row < num_rows - 1 and games_per_row == 1:
            sep_y = y_offset + adapter.game_height + block_spacing // 2
            draw.line((adapter.padding_x, sep_y, WIDTH - adapter.padding_x, sep_y), fill=(45, 45, 45))

    return canvas


def _render_scoreboard(adapter: ScoreboardV3Adapter, games: list[dict]) -> Image.Image:
    base = adapter.base_module
    canvas = _compose_canvas(adapter, games)

    dummy = Image.new("RGB", (WIDTH, 10), base.BACKGROUND_COLOR)
    dd = ImageDraw.Draw(dummy)
    try:
        l, t, r, b = dd.textbbox((0, 0), adapter.title, font=base.TITLE_FONT)
        title_h = b - t
    except Exception:
        _, title_h = dd.textsize(adapter.title, font=base.TITLE_FONT)

    league_logo = base._get_league_logo()
    logo_height = league_logo.height if league_logo else 0
    logo_gap = getattr(base, "LEAGUE_LOGO_GAP", 0) if league_logo else 0

    content_top = logo_height + logo_gap + title_h + getattr(base, "TITLE_GAP", 12)
    img_height = max(HEIGHT, content_top + canvas.height)
    img = Image.new("RGB", (WIDTH, img_height), base.BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    if league_logo:
        logo_x = (WIDTH - league_logo.width) // 2
        img.paste(league_logo, (logo_x, 0), league_logo)

    title_top = logo_height + logo_gap
    try:
        l, t, r, b = draw.textbbox((0, 0), adapter.title, font=base.TITLE_FONT)
        tw, th = r - l, b - t
        tx = (WIDTH - tw) // 2 - l
        ty = title_top - t
    except Exception:
        tw, th = draw.textsize(adapter.title, font=base.TITLE_FONT)
        tx = (WIDTH - tw) // 2
        ty = title_top
    draw.text((tx, ty), adapter.title, font=base.TITLE_FONT, fill=(255, 255, 255))

    img.paste(canvas, (0, content_top))
    return img


def _no_games_image(adapter: ScoreboardV3Adapter) -> Image.Image:
    base = adapter.base_module
    img = Image.new("RGB", (WIDTH, HEIGHT), base.BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    league_logo = base._get_league_logo()
    title_top = 0
    if league_logo:
        logo_x = (WIDTH - league_logo.width) // 2
        img.paste(league_logo, (logo_x, 0), league_logo)
        title_top = league_logo.height + getattr(base, "LEAGUE_LOGO_GAP", 0)
    try:
        l, t, r, b = draw.textbbox((0, 0), adapter.title, font=base.TITLE_FONT)
        tw, th = r - l, b - t
        tx = (WIDTH - tw) // 2 - l
        ty = title_top - t
    except Exception:
        tw, th = draw.textsize(adapter.title, font=base.TITLE_FONT)
        tx = (WIDTH - tw) // 2
        ty = title_top
    draw.text((tx, ty), adapter.title, font=base.TITLE_FONT, fill=(255, 255, 255))
    _left_align_text(
        draw,
        adapter.no_games_message,
        base.STATUS_FONT,
        adapter.padding_x,
        HEIGHT // 2 - base.STATUS_FONT.size,
        WIDTH - 2 * adapter.padding_x,
        base.STATUS_FONT.size * 2,
    )
    return img


def draw_stacked_logo_scoreboard(
    display,
    adapter: ScoreboardV3Adapter,
    *,
    transition: bool = False,
) -> ScreenImage:
    base = adapter.base_module
    games = adapter.fetch_games() or []

    if not games:
        clear_display(display)
        img = _no_games_image(adapter)
        if transition:
            return ScreenImage(img, displayed=False)
        display.image(img)
        time.sleep(getattr(base, "SCOREBOARD_SCROLL_PAUSE_BOTTOM", 1))
        return ScreenImage(img, displayed=True)

    full_img = _render_scoreboard(adapter, games)
    if transition:
        base._scroll_display(display, full_img)
        return ScreenImage(full_img, displayed=True)

    if full_img.height <= HEIGHT:
        display.image(full_img)
        time.sleep(getattr(base, "SCOREBOARD_SCROLL_PAUSE_BOTTOM", 1))
    else:
        base._scroll_display(display, full_img)
    return ScreenImage(full_img, displayed=True)

