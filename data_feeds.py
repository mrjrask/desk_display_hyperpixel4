"""Utilities for determining which data feeds need refreshing."""

from __future__ import annotations

from typing import Dict, Iterable, Set

# Screen IDs grouped by the cache key they rely on. Only screens that consume
# ``main.cache`` entries are included here; scoreboard-style screens fetch
# their own data on demand.
_FEED_DEPENDENCIES: Dict[str, Set[str]] = {
    "weather": {"weather1", "weather2", "weather hourly", "weather radar"},
    "bears": {"bears stand1", "bears stand2"},
    "hawks": {
        "hawks stand1",
        "hawks stand2",
        "hawks last",
        "hawks live",
        "hawks next",
        "hawks next home",
    },
    "bulls": {
        "bulls stand1",
        "bulls stand2",
        "bulls last",
        "bulls live",
        "bulls next",
        "bulls next home",
    },
    "cubs": {
        "cubs stand1",
        "cubs stand2",
        "cubs last",
        "cubs result",
        "cubs live",
        "cubs next",
        "cubs next home",
    },
    "sox": {
        "sox stand1",
        "sox stand2",
        "sox last",
        "sox live",
        "sox next",
        "sox next home",
    },
}


def required_feeds(requested_ids: Iterable[str]) -> Set[str]:
    """
    Return the set of cache keys that should be refreshed based on the active
    playlist.  When no schedule information is available, we conservatively
    assume that all feeds are required to preserve previous behaviour.
    """

    requested = set(requested_ids)
    if not requested:
        return set(_FEED_DEPENDENCIES.keys())

    return {
        feed
        for feed, dependent_screens in _FEED_DEPENDENCIES.items()
        if requested & dependent_screens
    }
