from __future__ import annotations

"""Shared helpers for locating writable storage directories."""

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

APP_DIR_NAME = "desk_display_hyperpixel4"


@dataclass(frozen=True)
class StoragePaths:
    """Resolved filesystem locations for runtime storage."""

    screenshot_dir: Path
    archive_base: Path


def _expand(path_str: str) -> Path:
    return Path(path_str).expanduser()


def _iter_candidate_roots() -> Iterable[Path]:
    env_root = os.environ.get("DESK_DISPLAY_DATA_DIR")
    if env_root:
        yield _expand(env_root)

    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        yield _expand(xdg_data) / APP_DIR_NAME

    yield Path.home() / ".local" / "share" / APP_DIR_NAME
    yield Path.home() / APP_DIR_NAME


def _iter_candidate_screenshot_dirs() -> Iterable[Path]:
    env_override = os.environ.get("DESK_DISPLAY_SCREENSHOT_DIR")
    if env_override:
        yield _expand(env_override)

    for root in _iter_candidate_roots():
        yield root / "screenshots"

    script_dir = Path(__file__).resolve().parent
    yield script_dir / "screenshots"


def _ensure_writable(path: Path, logger: Optional[logging.Logger]) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if logger:
            logger.debug("Could not create directory %s: %s", path, exc)
        return False

    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(path))
    except OSError as exc:
        if logger:
            logger.debug("Directory %s is not writable: %s", path, exc)
        return False

    os.close(fd)
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    return True


def _select_screenshot_dir(logger: Optional[logging.Logger]) -> Path:
    for candidate in _iter_candidate_screenshot_dirs():
        if _ensure_writable(candidate, logger):
            return candidate

    fallback = Path(__file__).resolve().parent / "screenshots"
    if logger:
        logger.warning(
            "Falling back to %s for screenshots; no writable directory was found.",
            fallback,
        )
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def resolve_storage_paths(*, logger: Optional[logging.Logger] = None) -> StoragePaths:
    """Return writable paths for screenshots and archives."""

    screenshot_dir = _select_screenshot_dir(logger)
    archive_base = screenshot_dir.parent / "screenshot_archive"
    archive_base.mkdir(parents=True, exist_ok=True)

    if logger:
        logger.info("Using screenshot directory %s", screenshot_dir)
        logger.info("Using screenshot archive base %s", archive_base)

    return StoragePaths(screenshot_dir=screenshot_dir, archive_base=archive_base)
