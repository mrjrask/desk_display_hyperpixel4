"""Tests for scoreboard status string formatting."""

import datetime

import pytest

from screens.mlb_scoreboard import _format_status as mlb_format_status
from screens.nfl_scoreboard import (
    _find_possession_side,
    _format_status as nfl_format_status,
    _team_identifier_tokens,
)


def _mlb_game(*, detailed: str, abstract: str = "preview", start: bool = True) -> dict:
    game = {
        "status": {
            "abstractGameState": abstract,
            "detailedState": detailed,
            "statusCode": "",
        },
        "linescore": {},
    }
    if start:
        game["_start_local"] = datetime.datetime(2024, 6, 1, 12, 30)
    return game


@pytest.mark.parametrize(
    "detailed, expected",
    [
        ("Warmup", "Warmup"),
        ("Delayed", "Delayed"),
        ("Postponed", "Postponed"),
    ],
)
def test_mlb_status_overrides_start_time(detailed: str, expected: str):
    game = _mlb_game(detailed=detailed)
    assert mlb_format_status(game) == expected


def _nfl_game(*, state: str, short: str = "", detail: str = "", clock: str = "", period=None) -> dict:
    return {
        "status": {
            "type": {
                "state": state,
                "shortDetail": short,
                "detail": detail,
            },
            "displayClock": clock,
            "period": period,
        }
    }


@pytest.mark.parametrize(
    "short_detail",
    ["End of the 1st", "Halftime", "End of the 3rd"],
)
def test_nfl_in_game_status_overrides_clock(short_detail: str):
    period = {"End of the 1st": 1, "Halftime": 2, "End of the 3rd": 3}[short_detail]
    game = _nfl_game(state="in", short=short_detail, detail=short_detail, clock="0:00", period=period)
    assert nfl_format_status(game) == short_detail


def test_team_identifier_tokens_filters_numeric_values():
    team = {
        "id": "4",
        "abbreviation": "CHI",
        "slug": "chicago-bears",
        "score": "14",
        "timeouts": 3,
        "linescores": [14, 0, 0, 0],
    }

    tokens = _team_identifier_tokens(team)

    assert "chi" in tokens
    assert "chicago-bears" in tokens
    assert "chicago" in tokens
    assert "bears" in tokens
    assert "4" in tokens  # Team ID preserved
    assert "14" not in tokens
    assert "3" not in tokens


def test_possession_side_prefers_team_id():
    game = {
        "competitors": [
            {"homeAway": "away", "team": {"id": "1", "abbreviation": "DET", "slug": "detroit-lions"}},
            {"homeAway": "home", "team": {"id": "2", "abbreviation": "CHI", "slug": "chicago-bears"}},
        ],
        "situation": {"possession": "2"},
    }

    assert _find_possession_side(game) == "home"


def test_possession_side_uses_identifier_tokens_without_numeric_collision():
    game = {
        "competitors": [
            {
                "homeAway": "away",
                "team": {
                    "id": "1",
                    "abbreviation": "CHI",
                    "slug": "chicago-bears",
                    "score": "14",
                },
            },
            {
                "homeAway": "home",
                "team": {
                    "id": "2",
                    "abbreviation": "GB",
                    "slug": "green-bay-packers",
                    "score": "14",
                },
            },
        ],
        "situation": {"possessionText": "CHI ball on CHI 45"},
    }

    assert _find_possession_side(game) == "away"


def test_possession_side_does_not_match_with_only_numeric_tokens():
    game = {
        "competitors": [
            {
                "homeAway": "away",
                "team": {
                    "id": "1",
                    "abbreviation": "BUF",
                    "slug": "buffalo-bills",
                    "score": "14",
                },
            },
            {
                "homeAway": "home",
                "team": {
                    "id": "2",
                    "abbreviation": "NYJ",
                    "slug": "new-york-jets",
                    "score": "14",
                },
            },
        ],
        "situation": {"possessionText": "14 play drive for 14 yards"},
    }

    assert _find_possession_side(game) is None


def test_possession_side_ignores_ambiguous_shared_tokens():
    game = {
        "competitors": [
            {
                "homeAway": "away",
                "team": {
                    "id": "1",
                    "abbreviation": "NYJ",
                    "slug": "new-york-jets",
                },
            },
            {
                "homeAway": "home",
                "team": {
                    "id": "2",
                    "abbreviation": "NYG",
                    "slug": "new-york-giants",
                },
            },
        ],
        "situation": {
            "lastPlay": {
                "team": {
                    "id": "2",
                    "abbreviation": "NYG",
                    "slug": "new-york-giants",
                }
            }
        },
    }

    assert _find_possession_side(game) == "home"

