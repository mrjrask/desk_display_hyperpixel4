import screens.mlb_team_standings as mlb_team_standings
import screens.nba_team_standings as nba_team_standings


def test_nba_standings_prefers_conference_rank(monkeypatch):
    captured = {}

    def fake_base(display, rec, logo_path, division_label, **kwargs):
        captured["divisionRank"] = rec.get("divisionRank")
        captured["division_label"] = division_label
        captured["conference_label"] = kwargs.get("conference_label")
        return rec

    monkeypatch.setattr(nba_team_standings, "_base_screen1", fake_base)

    rec = {
        "divisionRank": "0",
        "conferenceRank": 5,
        "leagueRecord": {"wins": 10, "losses": 5},
        "division": {"name": "Central"},
        "conference": {"name": "Eastern"},
    }

    nba_team_standings.draw_nba_standings_screen1(
        None,
        rec,
        "logo.png",
        transition=True,
    )

    assert captured["divisionRank"] == 5
    assert captured["division_label"] == "Eastern"
    assert captured["conference_label"] == "Eastern"


def test_nba_standings_falls_back_to_division_rank(monkeypatch):
    captured = {}

    def fake_base(display, rec, logo_path, division_label, **kwargs):
        captured["divisionRank"] = rec.get("divisionRank")
        captured["division_label"] = division_label
        captured["conference_label"] = kwargs.get("conference_label")
        return rec

    monkeypatch.setattr(nba_team_standings, "_base_screen1", fake_base)

    rec = {
        "divisionRank": 3,
        "leagueRecord": {"wins": 8, "losses": 7},
        "division": {"name": "Central"},
    }

    nba_team_standings.draw_nba_standings_screen1(
        None,
        rec,
        "logo.png",
        transition=True,
    )

    assert captured["divisionRank"] == 3
    assert captured["division_label"] == "Central"
    assert captured["conference_label"] is None
