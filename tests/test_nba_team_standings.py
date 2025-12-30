import screens.mlb_team_standings as mlb_team_standings
import screens.nba_team_standings as nba_team_standings


def test_nba_standings_uses_conference_rank(monkeypatch):
    captured = {}

    def fake_base(display, rec, logo_path, division_label, **kwargs):
        captured["divisionRank"] = rec.get("divisionRank")
        captured["conferenceRank"] = rec.get("conferenceRank")
        captured["division_label"] = division_label
        captured["conference_label"] = kwargs.get("conference_label")
        captured["pct"] = rec.get("leagueRecord", {}).get("pct")
        return rec

    monkeypatch.setattr(nba_team_standings, "_base_screen1", fake_base)

    rec = {
        "conferenceRank": 5,
        "divisionRank": 3,
        "leagueRecord": {"wins": 10, "losses": 5, "pct": 0.6001},
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
    assert captured["conferenceRank"] == 5
    assert captured["division_label"] == "Eastern"
    assert captured["conference_label"] == "Eastern"
    assert captured["pct"] == ".600"


def test_nba_standings_defaults_when_missing(monkeypatch):
    captured = {}

    def fake_base(display, rec, logo_path, division_label, **kwargs):
        captured["divisionRank"] = rec.get("divisionRank")
        captured["conferenceRank"] = rec.get("conferenceRank")
        captured["division_label"] = division_label
        captured["conference_label"] = kwargs.get("conference_label")
        return rec

    monkeypatch.setattr(nba_team_standings, "_base_screen1", fake_base)

    rec = {
        "leagueRecord": {"wins": 8, "losses": 7, "pct": "0.515"},
        "division": {"name": "Central"},
    }

    nba_team_standings.draw_nba_standings_screen1(
        None,
        rec,
        "logo.png",
        transition=True,
    )

    assert captured["divisionRank"] == "-"
    assert captured["conferenceRank"] == "-"
    assert captured["division_label"] == "conference"
    assert captured["conference_label"] == "conference"
