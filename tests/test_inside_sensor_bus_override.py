"""Tests for the INSIDE_SENSOR_I2C_BUS override handling."""

from typing import Iterable

import importlib
import inside_sensor


def _get_candidate_buses() -> Iterable[int]:
    importlib.reload(inside_sensor)
    return inside_sensor._candidate_buses()


def test_candidate_buses_default(monkeypatch):
    monkeypatch.delenv("INSIDE_SENSOR_I2C_BUS", raising=False)
    buses = _get_candidate_buses()
    assert list(buses) == [15, 13, 14, 1, 0, 10]


def test_candidate_buses_override_preferred(monkeypatch):
    monkeypatch.setenv("INSIDE_SENSOR_I2C_BUS", "7")
    buses = _get_candidate_buses()
    assert list(buses)[:3] == [7, 15, 13]
    assert 7 in buses


def test_candidate_buses_override_de_dupes(monkeypatch):
    monkeypatch.setenv("INSIDE_SENSOR_I2C_BUS", "1")
    buses = _get_candidate_buses()
    assert list(buses) == [1, 15, 13, 14, 0, 10]
