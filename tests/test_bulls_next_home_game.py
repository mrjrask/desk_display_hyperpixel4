"""Tests for Bulls next home game selection logic."""

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
