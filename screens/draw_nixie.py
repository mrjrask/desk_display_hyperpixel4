#!/usr/bin/env python3
"""Animated Nixie tube clock rendered with procedurally drawn digits."""

from __future__ import annotations

import datetime as dt
import logging
import time
from functools import lru_cache
from typing import Dict

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from config import HEIGHT, WIDTH, TIMES_SQUARE_FONT_PATH
from utils import ScreenImage, clear_display, log_call

BACKGROUND_COLOR = (3, 3, 8)
TUBE_COLOR = (24, 10, 6, 235)
TUBE_OUTLINE = (186, 120, 72, 255)
TUBE_HIGHLIGHT = (255, 214, 170, 90)
DIGIT_COLOR = (255, 232, 179, 255)
DIGIT_EDGE_COLOR = (255, 180, 90, 255)
GLOW_COLOR = (255, 118, 44, 220)

H_MARGIN = 28
V_MARGIN = 24
SPACING_RATIO = 0.12
COLON_RATIO = 0.28


@lru_cache(maxsize=32)
def _font_for_height(height: int) -> ImageFont.FreeTypeFont:
    target_height = max(20, height)
    size = int(round(target_height * 0.95))
    size = max(size, 24)

    while size > 8:
        font = ImageFont.truetype(TIMES_SQUARE_FONT_PATH, size=size)
        bbox = font.getbbox("0")
        text_height = bbox[3] - bbox[1]
        if text_height <= target_height * 0.92:
            return font
        size -= 1

    return ImageFont.truetype(TIMES_SQUARE_FONT_PATH, size=10)


@lru_cache(maxsize=128)
def _digit_image(height: int, value: str) -> Image.Image:
    font = _font_for_height(height)
    padding_x = max(6, int(round(height * 0.1)))
    bbox = font.getbbox(value)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    canvas_height = max(height, text_height + padding_x)
    img = Image.new("RGBA", (text_width + padding_x * 2, canvas_height), (0, 0, 0, 0))

    # Vertical alignment keeps the digits visually centered within the tube.
    offset_y = (canvas_height - text_height) // 2 - bbox[1]
    text_position = (padding_x - bbox[0], offset_y)

    glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.text(text_position, value, fill=GLOW_COLOR, font=font)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=max(3, int(round(height * 0.12)))))

    digit_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    digit_draw = ImageDraw.Draw(digit_layer)
    digit_draw.text(text_position, value, fill=DIGIT_COLOR, font=font)
    stroke_width = max(1, int(round(height * 0.04)))
    digit_draw.text(
        text_position,
        value,
        fill=DIGIT_COLOR,
        font=font,
        stroke_width=stroke_width,
        stroke_fill=DIGIT_EDGE_COLOR,
    )

    combined = Image.new("RGBA", img.size, (0, 0, 0, 0))
    combined = Image.alpha_composite(combined, glow_layer)
    combined = Image.alpha_composite(combined, digit_layer)

    # Subtle glass reflection
    highlight = Image.new("RGBA", img.size, (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight)
    highlight_height = max(2, int(round(canvas_height * 0.18)))
    highlight_draw.rectangle(
        (
            int(padding_x * 0.3),
            int(canvas_height * 0.12),
            int(img.width * 0.35),
            int(canvas_height * 0.12) + highlight_height,
        ),
        fill=TUBE_HIGHLIGHT,
    )
    highlight = highlight.filter(ImageFilter.GaussianBlur(radius=max(2, int(round(height * 0.05)))))
    combined = Image.alpha_composite(combined, highlight)

    return combined


@lru_cache(maxsize=32)
def _digits_for_height(height: int) -> Dict[str, Image.Image]:
    return {value: _digit_image(height, value) for value in "0123456789"}


@lru_cache(maxsize=32)
def _colon_image(height: int) -> Image.Image:
    height = max(12, height)
    width = max(12, int(round(height * COLON_RATIO)))
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    dots = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dot_draw = ImageDraw.Draw(dots)

    top_cy = int(round(height * 0.32))
    bottom_cy = int(round(height * 0.68))
    radius = max(2, int(round(height * 0.08)))
    glow_radius = max(radius + 2, int(round(height * 0.18)))
    center_x = width // 2

    for cy in (top_cy, bottom_cy):
        glow_draw.ellipse(
            (
                center_x - glow_radius,
                cy - glow_radius,
                center_x + glow_radius,
                cy + glow_radius,
            ),
            fill=(252, 121, 44, 110),
        )
        dot_draw.ellipse(
            (
                center_x - radius,
                cy - radius,
                center_x + radius,
                cy + radius,
            ),
            fill=(255, 248, 138, 255),
        )

    combined = Image.alpha_composite(glow, dots)
    return combined


def _tube_rectangles(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int) -> None:
    pad_x = max(10, int(round(height * 0.22)))
    pad_y = max(12, int(round(height * 0.28)))
    radius = max(12, int(round(height * 0.24)))
    outline_width = max(2, int(round(height * 0.05)))

    rect = (x - pad_x, y - pad_y, x + width + pad_x, y + height + pad_y)
    draw.rounded_rectangle(rect, fill=TUBE_COLOR, outline=TUBE_OUTLINE, width=outline_width, radius=radius)

    # Inner glow inside the tube
    inner_margin = max(4, int(round(height * 0.08)))
    inner_rect = (
        rect[0] + inner_margin,
        rect[1] + inner_margin,
        rect[2] - inner_margin,
        rect[3] - inner_margin,
    )
    draw.rounded_rectangle(inner_rect, outline=TUBE_HIGHLIGHT, width=max(1, outline_width - 1), radius=max(4, radius - inner_margin))


def _compose_frame(now: dt.datetime | None = None) -> Image.Image:
    now = now or dt.datetime.now()
    time_digits = now.strftime("%H%M%S")
    elements = [time_digits[0], time_digits[1], ":", time_digits[2], time_digits[3], ":", time_digits[4], time_digits[5]]

    available_height = max(1, HEIGHT - V_MARGIN * 2)
    available_width = max(1, WIDTH - H_MARGIN * 2)
    gap_count = len(elements) - 1

    digits_scaled = _digits_for_height(available_height)
    sample = digits_scaled["0"]
    digit_ratio = sample.width / float(sample.height)

    total_ratio = digit_ratio * 6 + COLON_RATIO * 2 + SPACING_RATIO * gap_count
    height_by_width = int(round(available_width / total_ratio))
    target_height = max(48, min(available_height, height_by_width))
    spacing = max(8, int(round(target_height * SPACING_RATIO)))

    digits_scaled = _digits_for_height(target_height)
    colon_img = _colon_image(target_height)

    element_widths = []
    for item in elements:
        if item == ":":
            element_widths.append(colon_img.width)
        else:
            element_widths.append(digits_scaled[item].width)

    total_width = sum(element_widths) + spacing * gap_count
    x = max(H_MARGIN, (WIDTH - total_width) // 2)
    y = max(V_MARGIN, (HEIGHT - target_height) // 2)

    frame = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(frame, "RGBA")

    for item, width_px in zip(elements, element_widths):
        _tube_rectangles(draw, x, y, width_px, target_height)
        if item == ":":
            frame.paste(colon_img, (x, y), colon_img)
        else:
            digit_img = digits_scaled[item]
            frame.paste(digit_img, (x, y), digit_img)
        x += width_px + spacing

    return frame


def _play_flicker(display, base: Image.Image) -> None:
    enhancer = ImageEnhance.Brightness(base)
    for factor in (0.94, 1.06, 1.0):
        frame = enhancer.enhance(factor)
        try:
            display.image(frame)
            if hasattr(display, "show"):
                display.show()
        except Exception:  # pragma: no cover - defensive refresh guard
            break
        time.sleep(0.08)


@log_call
def draw_nixie(display, transition: bool = False):
    frame = _compose_frame()

    if transition:
        return frame

    clear_display(display)
    try:
        display.image(frame)
        if hasattr(display, "show"):
            display.show()
    except Exception:  # pragma: no cover - defensive refresh guard
        logging.exception("Failed to render Nixie clock")
        return ScreenImage(frame, displayed=False)

    _play_flicker(display, frame)
    return ScreenImage(frame, displayed=True)
