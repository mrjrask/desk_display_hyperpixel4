from PIL import Image

from screen_overrides import ResolvedScreenOverride
from screen_runtime_overrides import apply_override_to_image, apply_override_to_result
from utils import ScreenImage
from config import WIDTH, HEIGHT


def test_apply_override_to_image_scales_result():
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    override = ResolvedScreenOverride(font_scale=0.5)

    adjusted = apply_override_to_image(image, override)

    assert adjusted.size == (WIDTH, HEIGHT)
    assert adjusted is not image


def test_apply_override_to_result_handles_screen_image_display_flag():
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    result = ScreenImage(image=image, displayed=True)
    override = ResolvedScreenOverride(image_scale=0.8)

    adjusted = apply_override_to_result(result, override)

    assert isinstance(adjusted, ScreenImage)
    assert adjusted.image.size == (WIDTH, HEIGHT)
    assert not adjusted.displayed


def test_apply_override_to_image_respects_device_profile():
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    override = ResolvedScreenOverride(device_profile="hyperpixel4")

    adjusted = apply_override_to_image(image, override)

    assert adjusted.size == (800, 480)
