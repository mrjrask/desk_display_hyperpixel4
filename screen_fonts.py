from __future__ import annotations

from typing import Dict, List, Sequence

import config


# Mapping of screen IDs to font groups defined in ``config``.
SCREEN_FONT_GROUPS: Dict[str, List[str]] = {
    "date": ["date_time"],
    "time": ["date_time"],
    "weather1": ["weather", "shared"],
    "weather2": ["weather", "shared"],
    "weather hourly": ["weather", "shared"],
    "weather radar": ["weather", "shared"],
    "inside": ["inside"],
    "inside sensors": ["inside"],
    "vrnof": ["vrnof"],
    "travel": ["travel"],
}

# Logo-oriented screens don't use fonts directly.
LOGO_SCREENS: Sequence[str] = (
    "weather logo",
    "verano logo",
    "bears logo",
    "nfl logo",
    "mlb logo",
    "nba logo",
    "hawks logo",
    "bulls logo",
    "nhl logo",
    "cubs logo",
    "sox logo",
)
for logo in LOGO_SCREENS:
    SCREEN_FONT_GROUPS.setdefault(logo, [])

SPORTS_SCREENS: Sequence[str] = (
    "bears next",
    "NFL Scoreboard",
    "NFL Scoreboard v2",
    "NFL Overview NFC",
    "NFL Overview AFC",
    "NFL Standings NFC",
    "NFL Standings AFC",
    "hawks last",
    "hawks live",
    "hawks next",
    "hawks next home",
    "bulls last",
    "bulls live",
    "bulls next",
    "bulls next home",
    "NHL Scoreboard",
    "NHL Scoreboard v2",
    "NHL Standings Overview West",
    "NHL Standings Overview East",
    "NHL Standings West",
    "NHL Standings East",
    "NHL Standings Overview v2 West",
    "NHL Standings Overview v2 East",
    "cubs last",
    "cubs result",
    "cubs live",
    "cubs next",
    "cubs next home",
    "sox last",
    "sox live",
    "sox next",
    "sox next home",
    "MLB Scoreboard",
    "MLB Scoreboard v2",
    "MLB Scoreboard v3",
    "NBA Scoreboard",
    "NBA Scoreboard v2",
)
for screen in SPORTS_SCREENS:
    SCREEN_FONT_GROUPS.setdefault(screen, ["sports"])

STANDINGS_SCREENS: Sequence[str] = (
    "cubs stand1",
    "cubs stand2",
    "sox stand1",
    "sox stand2",
    "hawks stand1",
    "hawks stand2",
    "bulls stand1",
    "bulls stand2",
)
for screen in STANDINGS_SCREENS:
    SCREEN_FONT_GROUPS.setdefault(screen, ["mlb_standings"])

SCREEN_FONT_GROUPS.setdefault("bears stand1", ["mlb_standings", "nfl_standings"])
SCREEN_FONT_GROUPS.setdefault("bears stand2", ["mlb_standings", "nfl_standings"])

MLB_STANDINGS_SCREENS: Sequence[str] = (
    "NL Overview",
    "NL East",
    "NL Central",
    "NL West",
    "NL Wild Card",
    "AL Overview",
    "AL East",
    "AL Central",
    "AL West",
    "AL Wild Card",
)
for screen in MLB_STANDINGS_SCREENS:
    SCREEN_FONT_GROUPS.setdefault(screen, ["mlb_standings"])

CUSTOM_SCREEN_FONTS: Dict[str, List[Dict[str, object]]] = {
    "nixie": [
        {
            "group": "nixie",
            "key": "digits",
            "name": "TimesSquare-m105.ttf",
            "size": "adaptive",
            "path": config.TIMES_SQUARE_FONT_PATH,
        }
    ]
}


def font_definitions_for_screen(screen_id: str) -> List[Dict[str, object]]:
    """Return structured font metadata for a given screen ID."""

    registry = config.get_font_definitions()
    groups = SCREEN_FONT_GROUPS.get(screen_id, [])
    fonts: List[Dict[str, object]] = []
    seen = set()

    for group in groups:
        group_fonts = registry.get(group, {})
        if not isinstance(group_fonts, dict):
            continue
        for font_key, meta in sorted(group_fonts.items()):
            if not isinstance(meta, dict):
                continue
            signature = (group, font_key, meta.get("name"), meta.get("size"))
            if signature in seen:
                continue
            fonts.append(
                {
                    "group": group,
                    "key": font_key,
                    "name": meta.get("name") or "",
                    "size": meta.get("size"),
                    "path": meta.get("path") or "",
                }
            )
            seen.add(signature)

    fonts.extend(CUSTOM_SCREEN_FONTS.get(screen_id, []))
    return fonts
