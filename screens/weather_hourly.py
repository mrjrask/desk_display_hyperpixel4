"""Hourly weather screen entrypoint with emoji-free precipitation icons.

This module forwards to :func:`screens.draw_weather.draw_weather_hourly` so
callers that import the legacy ``weather_hourly`` module pick up the updated
rendering that replaces precipitation emoji glyphs with drawn vector icons.
"""

from screens.draw_weather import draw_weather_hourly

__all__ = ["draw_weather_hourly"]
