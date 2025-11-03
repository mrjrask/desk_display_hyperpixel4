"""Tests covering display profile resolution overrides."""

import importlib
from typing import Dict

import pytest

import config as config_module

_DISPLAY_ENV_VARS = ["DISPLAY_PROFILE", "DISPLAY_WIDTH", "DISPLAY_HEIGHT"]


@pytest.fixture
def reload_config(monkeypatch):
    """Reload ``config`` with the provided environment overrides."""

    def _reload(overrides: Dict[str, str]):
        for key in _DISPLAY_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        for key, value in overrides.items():
            monkeypatch.setenv(key, value)
        return importlib.reload(config_module)

    yield _reload

    importlib.reload(config_module)


def test_hyperpixel4_landscape_dimensions(reload_config):
    config = reload_config({"DISPLAY_PROFILE": "hyperpixel4_landscape"})

    assert (config.WIDTH, config.HEIGHT) == (800, 480)


def test_landscape_aliases_point_to_rectangular_panel(reload_config):
    for alias in ("hp4", "hp4_landscape", "landscape"):
        config = reload_config({"DISPLAY_PROFILE": alias})
        assert (config.WIDTH, config.HEIGHT) == (800, 480)


def test_portrait_aliases_select_portrait_layout(reload_config):
    for alias in ("hyperpixel4_portrait", "hp4_portrait", "portrait"):
        config = reload_config({"DISPLAY_PROFILE": alias})
        assert (config.WIDTH, config.HEIGHT) == (480, 800)
