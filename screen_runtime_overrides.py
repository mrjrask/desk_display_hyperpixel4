"""Runtime helpers for applying screen overrides."""
from __future__ import annotations

from typing import Optional, Tuple, Union

from PIL import Image, ImageOps

from config import HEIGHT, WIDTH, get_display_geometry
from screen_overrides import ResolvedScreenOverride
from utils import ScreenImage


def _target_canvas_size(override: ResolvedScreenOverride) -> Tuple[int, int]:
    if override.device_profile:
        geometry = get_display_geometry(override.device_profile)
        if geometry:
            return geometry
    return WIDTH, HEIGHT


def _scale_image(image: Image.Image, factor: Optional[float]) -> Image.Image:
    if factor is None or factor <= 0:
        return image
    if abs(factor - 1.0) < 0.0001:
        return image
    width = max(1, int(round(image.width * factor)))
    height = max(1, int(round(image.height * factor)))
    if (width, height) == image.size:
        return image
    return image.resize((width, height), Image.LANCZOS)


def _fit_canvas(image: Image.Image, canvas_size: Tuple[int, int]) -> Image.Image:
    if image.size == canvas_size:
        return image
    fitted = ImageOps.contain(image, canvas_size, Image.LANCZOS)
    if fitted.size == canvas_size:
        return fitted
    canvas = Image.new(image.mode, canvas_size, "black")
    offset = ((canvas_size[0] - fitted.width) // 2, (canvas_size[1] - fitted.height) // 2)
    canvas.paste(fitted, offset)
    return canvas


def apply_override_to_image(image: Image.Image, override: ResolvedScreenOverride) -> Image.Image:
    """Return ``image`` adjusted according to ``override``."""

    scale = override.image_scale if override.image_scale is not None else override.font_scale
    scaled = _scale_image(image, scale)
    canvas_size = _target_canvas_size(override)
    return _fit_canvas(scaled, canvas_size)


def apply_override_to_result(
    result: Union[Image.Image, ScreenImage, None],
    override: Optional[ResolvedScreenOverride],
) -> Union[Image.Image, ScreenImage, None]:
    """Apply ``override`` to ``result`` if possible."""

    if result is None or not override:
        return result

    image: Optional[Image.Image]
    was_screen_image = isinstance(result, ScreenImage)
    if was_screen_image:
        image = result.image
    elif isinstance(result, Image.Image):
        image = result
    else:
        return result

    adjusted = apply_override_to_image(image, override)
    if adjusted is image:
        return result

    if was_screen_image:
        return ScreenImage(image=adjusted, displayed=False, led_override=result.led_override)
    return adjusted
