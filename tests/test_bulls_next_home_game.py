"""Tests for Bulls next home game selection logic."""

import datetime

import data_fetch


def _home_game(state: str) -> dict:
    return {
        "teams": {
            "home": {"team": {"id": data_fetch.NBA_TEAM_ID}},
            "away": {"team": {"id": "0000000000"}},
        },
        "status": {"detailedState": state},
    }


def test_bulls_next_home_prefers_scheduled_over_placeholder(monkeypatch):
    placeholder = _home_game("TBD")
    scheduled = _home_game("Scheduled")

    def _fake_future(_days_forward):
        yield from (placeholder, scheduled)

    monkeypatch.setattr(data_fetch, "_future_bulls_games", _fake_future)

    assert data_fetch.fetch_bulls_next_home_game() is scheduled


def test_bulls_next_home_returns_first_non_final_home_game(monkeypatch):
    non_home = {
        "teams": {
            "home": {"team": {"id": "0000000000"}},
            "away": {"team": {"id": data_fetch.NBA_TEAM_ID}},
        },
        "status": {"detailedState": "Scheduled"},
    }
    fallback = _home_game("TBD")
    final_game = _home_game("Final")

    def _fake_future(_days_forward):
        yield from (non_home, fallback, final_game)

    monkeypatch.setattr(data_fetch, "_future_bulls_games", _fake_future)

    assert data_fetch.fetch_bulls_next_home_game() is fallback


def test_bulls_next_home_falls_back_to_ics(monkeypatch):
    monkeypatch.setattr(data_fetch, "_future_bulls_games", lambda _days_forward: iter(()))

    ics_game = {"teams": {"home": {"team": {"id": str(data_fetch.NBA_TEAM_ID)}}}}

    monkeypatch.setattr(
        data_fetch, "_future_bulls_home_games_from_ics", lambda _days_forward: iter((ics_game,))
    )

    assert data_fetch.fetch_bulls_next_home_game() is ics_game


def test_bulls_next_home_extends_ics_window(monkeypatch):
    monkeypatch.setattr(data_fetch, "_future_bulls_games", lambda _days_forward: iter(()))

    target_game = {"teams": {"home": {"team": {"id": str(data_fetch.NBA_TEAM_ID)}}}}
    seen_windows = []

    def _fake_ics(days_forward):
        seen_windows.append(days_forward)
        if days_forward == data_fetch._NBA_HOME_GAME_EXTENDED_LOOKAHEAD_DAYS:
            return iter((target_game,))
        return iter(())

    monkeypatch.setattr(data_fetch, "_future_bulls_home_games_from_ics", _fake_ics)

    assert data_fetch.fetch_bulls_next_home_game() is target_game
    assert seen_windows == [data_fetch._NBA_LOOKAHEAD_DAYS, data_fetch._NBA_HOME_GAME_EXTENDED_LOOKAHEAD_DAYS]


def test_parse_bulls_ics_shapes_game_correctly():
    feed = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Chicago Bulls vs. Miami Heat
DTSTART;TZID=America/Chicago:20241005T190000
LOCATION:United Center
END:VEVENT
END:VCALENDAR
"""

    events = data_fetch._parse_bulls_ics(feed)
    assert len(events) == 1

    game = data_fetch._ics_event_to_game(events[0])
    assert game

    assert game["teams"]["home"]["team"]["id"] == str(data_fetch.NBA_TEAM_ID)
    assert game["teams"]["away"]["team"]["triCode"] == "MIA"

    start = game.get("_start_local")
    assert isinstance(start, datetime.datetime)
    assert start.hour == 19
    assert start.tzinfo
    assert start.astimezone(data_fetch.CENTRAL_TIME).hour == 19
