"""Tests for the preferred bus ordering helper used by SensorHub."""

from typing import List

import screens.draw_inside as draw_inside


def _call_helper(values: List[int]) -> List[int]:
    return draw_inside._preferred_bus_order(values)


def test_preferred_bus_order_defaults(monkeypatch):
    monkeypatch.setattr(draw_inside, "INSIDE_SENSOR_I2C_BUS", None, raising=False)
    assert _call_helper([1, 5, 15, 13, 15, 2]) == [15, 13, 1, 2, 5]


def test_preferred_bus_order_with_override(monkeypatch):
    monkeypatch.setattr(draw_inside, "INSIDE_SENSOR_I2C_BUS", 13, raising=False)
    assert _call_helper([1, 5, 15, 13, 15, 2]) == [13, 15, 1, 2, 5]


def test_override_inserts_when_missing(monkeypatch):
    monkeypatch.setattr(draw_inside, "INSIDE_SENSOR_I2C_BUS", 7, raising=False)
    assert _call_helper([1, 5, 15]) == [7, 15, 1, 5]
