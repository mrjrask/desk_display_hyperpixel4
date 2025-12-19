import pytest
from PIL import Image, ImageDraw

import data_fetch
from screens import draw_weather
from utils import ScreenImage


class _DummyDisplay:
    def clear(self):
        pass

    def image(self, _):
        pass

    def show(self):
        pass


def test_weatherkit_defaults_to_celsius_when_units_missing(monkeypatch):
    payload = {
        "currentWeather": {
            "asOf": 1720000000,
            "temperature": 21,
            "apparentTemperature": 19,
            "humidity": 40,
            "pressure": 1012,
            "windSpeed": 5,
            "windDirection": 90,
            "uvIndex": 3,
            "conditionCode": "Cloudy",
            "isDaylight": True,
            "cloudCover": 0.42,
        },
        "forecastDaily": {
            "days": [
                {
                    "forecastStart": 1720000000,
                    "sunriseTime": 1720003600,
                    "sunsetTime": 1720042800,
                    "highTemperature": 20,
                    "lowTemperature": 10,
                    "conditionCode": "Clear",
                    "precipitationAmount": 0,
                }
            ]
        },
    }

    daily = data_fetch._map_daily_forecast(payload)
    current = data_fetch._map_current_weather(payload, daily)

    assert daily[0]["temp"]["max"] == pytest.approx(68.0)
    assert daily[0]["temp"]["min"] == pytest.approx(50.0)
    assert current["temp"] == pytest.approx(69.8)
    assert current["feels_like"] == pytest.approx(66.2)
    assert current["clouds"] == pytest.approx(42.0)

    recorded_text = []
    original_text = ImageDraw.ImageDraw.text

    def _recording_text(self, xy, text, *args, **kwargs):
        recorded_text.append(str(text))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", _recording_text)
    monkeypatch.setattr(
        draw_weather,
        "fetch_weather_icon",
        lambda *_, **__: Image.new(
            "RGBA", (draw_weather.WEATHER_ICON_SIZE, draw_weather.WEATHER_ICON_SIZE), (0, 0, 0, 0)
        ),
    )

    screen = draw_weather.draw_weather_screen_1(
        _DummyDisplay(), {"current": current, "daily": daily, "hourly": []}, transition=True
    )

    assert isinstance(screen, ScreenImage)
    assert any("70°F" in text for text in recorded_text)
    assert "66°" in recorded_text
    assert "68°" in recorded_text
    assert "50°" in recorded_text
    assert "42%" in recorded_text
