import screens.nhl_team_standings as nhl_team_standings


def test_nhl_standings_show_division_and_conference(monkeypatch):
    captured = {}

    monkeypatch.setattr(nhl_team_standings, "IS_SQUARE_DISPLAY", True)

    def fake_base(display, rec, logo_path, division_label, **kwargs):
        captured["divisionRank"] = rec.get("divisionRank")
        captured["conferenceRank"] = rec.get("conferenceRank")
        captured["division_label"] = division_label
        captured["conference_label"] = kwargs.get("conference_label")
        captured["conferenceName"] = rec.get("conferenceName")
        captured["divisionName"] = rec.get("divisionName")
        return rec

    monkeypatch.setattr(nhl_team_standings, "_base_screen1", fake_base)

    rec = {
        "divisionRank": 2,
        "conferenceRank": 5,
        "leagueRecord": {"wins": 20, "losses": 15, "pct": "0.576"},
        "division": {"name": "Central Division"},
        "conference": {"name": "Western Conference"},
    }

    nhl_team_standings.draw_nhl_standings_screen1(
        None,
        rec,
        "logo.png",
        division_name="Central",
        transition=True,
    )

    assert captured["divisionRank"] == 2
    assert captured["conferenceRank"] == 5
    assert captured["division_label"] == "Central"
    assert captured["conference_label"] == "conference"
    assert captured["conferenceName"] == "the West"
    assert captured["divisionName"] == "Central"


def test_nhl_standings_show_full_conference_for_rect(monkeypatch):
    captured = {}

    def fake_base(display, rec, logo_path, division_label, **kwargs):
        captured["conferenceName"] = rec.get("conferenceName")
        return rec

    monkeypatch.setattr(nhl_team_standings, "_base_screen1", fake_base)
    monkeypatch.setattr(nhl_team_standings, "IS_SQUARE_DISPLAY", False)

    rec = {
        "leagueRecord": {"wins": 20, "losses": 15, "pct": "0.576"},
        "conference": {"name": "Western Conference"},
    }

    nhl_team_standings.draw_nhl_standings_screen1(
        None,
        rec,
        "logo.png",
        division_name="Central",
        transition=True,
    )

    assert captured["conferenceName"] == "Western Conf."
