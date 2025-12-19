import screens.mlb_team_standings as mlb_team_standings
import screens.nba_team_standings as nba_team_standings


def test_nba_standings_prefers_conference_rank(monkeypatch):
    captured = {}

    def fake_base(display, rec, logo_path, division_label, **kwargs):
        captured["divisionRank"] = rec.get("divisionRank")
        try:
            rank_val = int(rec.get("divisionRank"))
            rank_label = mlb_team_standings._ord(rank_val)
        except Exception:
            rank_label = rec.get("divisionRank")
        captured["rank_text"] = f"{rank_label} in {division_label}"
        return rec

    monkeypatch.setattr(nba_team_standings, "_base_screen1", fake_base)

    rec = {
        "divisionRank": "0",
        "conferenceRank": 5,
        "leagueRecord": {"wins": 10, "losses": 5},
        "division": {"name": "Central"},
    }

    nba_team_standings.draw_nba_standings_screen1(
        None,
        rec,
        "logo.png",
        transition=True,
    )

    assert captured["divisionRank"] == 5
    assert captured["rank_text"].startswith("5th in Central")
