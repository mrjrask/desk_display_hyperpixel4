"""Lazy-loading helpers for screen logos.

Images are resized on first access instead of during module import to avoid
inflating startup time and memory usage when logo-only screens are disabled.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Callable, Dict, Iterable, Iterator, Optional

from PIL import Image

import config

LOGO_SCROLL_HEIGHT = max(1, config.HEIGHT - 30)  # Leave a 30px margin while filling the display


def _load_logo(
    filename: str, *, height: int = LOGO_SCROLL_HEIGHT, width: Optional[int] = None
) -> Optional[Image.Image]:
    path = os.path.join(config.IMAGES_DIR, filename)
    try:
        with Image.open(path) as img:
            has_transparency = img.mode in {"RGBA", "LA"} or (
                img.mode == "P" and "transparency" in img.info
            )
            target_mode = "RGBA" if has_transparency else "RGB"
            img = img.convert(target_mode)
            if width is not None and img.width:
                ratio = width / float(img.width)
                target_w = max(1, int(round(img.width * ratio)))
                target_h = max(1, int(round(img.height * ratio)))
            else:
                ratio = height / float(img.height) if img.height else 1
                target_h = max(1, int(round(img.height * ratio))) if img.height else height
                target_w = max(1, int(round(img.width * ratio))) if img.width else max(1, height)
            resized = img.resize((target_w, target_h), Image.ANTIALIAS)
        return resized
    except Exception as exc:
        logging.warning("Logo load failed '%s': %s", filename, exc)
        return None


class LazyLogoMap(Mapping[str, Optional[Image.Image]]):
    """Dictionary-like container that lazy-loads and caches logos on demand."""

    def __init__(self, loaders: Dict[str, Callable[[], Optional[Image.Image]]]):
        self._loaders = loaders
        self._cache: Dict[str, Optional[Image.Image]] = {}

    def _load(self, key: str) -> Optional[Image.Image]:
        if key in self._cache:
            return self._cache[key]

        loader = self._loaders.get(key)
        if loader is None:
            return None

        logo = loader()
        self._cache[key] = logo
        return logo

    def get(self, key: str, default=None):  # type: ignore[override]
        if key not in self._loaders:
            return default
        return self._load(key)

    def __getitem__(self, key: str) -> Optional[Image.Image]:
        if key not in self._loaders:
            raise KeyError(key)
        return self._load(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._loaders)

    def __len__(self) -> int:
        return len(self._loaders)

    def preload(self, keys: Optional[Iterable[str]] = None) -> None:
        """Force-load a subset (or all) logos into the cache."""

        targets = keys if keys is not None else self._loaders.keys()
        for key in targets:
            if key in self._loaders:
                self._load(key)


def build_logo_map() -> LazyLogoMap:
    loaders: Dict[str, Callable[[], Optional[Image.Image]]] = {}
    logo_map = LazyLogoMap(loaders)

    def _team_logo_loader(path: str) -> Callable[[], Optional[Image.Image]]:
        def _loader() -> Optional[Image.Image]:
            base_logo = logo_map.get("bears logo")
            team_logo_width = base_logo.width if isinstance(base_logo, Image.Image) else None
            return _load_logo(path, width=team_logo_width)

        return _loader

    loaders.update(
        {
            "weather logo": lambda: _load_logo("weather.jpg"),
            "verano logo": lambda: _load_logo("verano.jpg"),
            "bears logo": lambda: _load_logo("nfl/chi.png"),
            "nfl logo": lambda: _load_logo("nfl/nfl.png"),
            "hawks logo": _team_logo_loader("nhl/CHI.png"),
            "nhl logo": lambda: _load_logo("nhl/nhl.png")
            or _load_logo("nhl/NHL.png"),
            "cubs logo": _team_logo_loader("mlb/CUBS.png"),
            "sox logo": _team_logo_loader("mlb/SOX.png"),
            "mlb logo": lambda: _load_logo("mlb/MLB.png"),
            "nba logo": lambda: _load_logo("nba/NBA.png"),
            "bulls logo": _team_logo_loader("nba/CHI.png"),
        }
    )

    return logo_map
