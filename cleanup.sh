#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

echo "⏱  Running cleanup at $(date +%Y%m%d_%H%M%S)…"

# Work from the repo root (script directory)
dir="$(cd -- "$(dirname "$0")" && pwd)"
cd "$dir"

# Defaults (can be overridden via env)
SCREENSHOTS_DIR="${SCREENSHOTS_DIR:-${dir}/screenshots}"
ARCHIVE_ROOT="${ARCHIVE_ROOT:-${dir}/screenshot_archive}"
ARCHIVE_DEFAULT_FOLDER="${ARCHIVE_DEFAULT_FOLDER:-_unsorted}"

# --- 1) Clear the display (only when safe) ---
echo "    → Clearing display…"

if [[ -n "${WAYLAND_DISPLAY:-}" && -z "${DISPLAY:-}" ]]; then
  echo "      Skipped (Wayland session without X11: no safe GL context for pygame)."
else
  python3 - <<'PY'
import logging, os
logging.basicConfig(level=logging.INFO, format="      %(message)s")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Best-effort KMSDRM when not under X/Wayland (headless TTY)
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")

try:
    from utils import Display, clear_display
except Exception as exc:  # pragma: no cover
    logging.warning("Display cleanup skipped: import failed: %s", exc)
else:
    try:
        d = Display()
        clear_display(d)
        try:
            import pygame
            try: pygame.display.flip()
            except Exception: pass
            try: pygame.display.quit()
            except Exception: pass
            try: pygame.quit()
            except Exception: pass
        except Exception:
            pass
        logging.info("Display cleared.")
    except Exception as exc:  # pragma: no cover
        logging.warning("Display cleanup failed (soft): %s", exc)
PY
fi

# --- 2) Archive leftover screenshots/videos ---
if [[ -d "${SCREENSHOTS_DIR}" ]]; then
  mapfile -d '' -t leftover_files < <(
    find "${SCREENSHOTS_DIR}" -type f \
      \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \
         -o -iname '*.mp4' -o -iname '*.avi' \) -print0 | sort -z
  )
else
  leftover_files=()
fi

if (( ${#leftover_files[@]} > 0 )); then
  echo "    → Archiving leftover screenshots/videos to screenshot_archive/<screen>/…"
  for src in "${leftover_files[@]}"; do
    rel_path="${src#${SCREENSHOTS_DIR}/}"
    screen_folder="${ARCHIVE_DEFAULT_FOLDER}"
    remainder="${rel_path}"

    if [[ "${rel_path}" != "${src}" ]]; then
      IFS='/' read -r first rest <<< "${rel_path}"
      if [[ -n "${rest}" ]]; then
        screen_folder="${first}"
        remainder="${rest}"
      fi
    fi

    dest_dir="${ARCHIVE_ROOT}/${screen_folder}"
    dest="${dest_dir}/${remainder}"
    mkdir -p "$(dirname "${dest}")"
    mv -f "${src}" "${dest}"
  done

  # Clean up any empty dirs left under screenshots/
  if [[ -d "${SCREENSHOTS_DIR}" ]]; then
    find "${SCREENSHOTS_DIR}" -type d -empty -delete
  fi
else
  echo "    → No leftover screenshots/videos to archive."
fi

# --- 3) Remove Python bytecode caches (skip venv/.git/archive) ---
echo "    → Removing Python bytecode (__pycache__, *.pyc, *.pyo)…"

# Build a pruned find that skips common exclusions
# (Add more -path … -prune entries if you have other large dirs to ignore.)
find_pruned() {
  find . \
    -path "./venv" -prune -o \
    -path "./.git" -prune -o \
    -path "./screenshot_archive" -prune -o \
    "$@"
}

# Remove __pycache__ directories
mapfile -d '' -t _pycache_dirs < <(find_pruned -type d -name "__pycache__" -print0)
if (( ${#_pycache_dirs[@]} > 0 )); then
  printf '%s\0' "${_pycache_dirs[@]}" | xargs -0r rm -rf --
  echo "      Removed ${#_pycache_dirs[@]} __pycache__ director$( (( ${#_pycache_dirs[@]} == 1 )) && echo 'y' || echo 'ies')."
else
  echo "      No __pycache__ directories found."
fi

# Remove *.pyc / *.pyo files
mapfile -d '' -t _pyc_files < <(find_pruned -type f \( -name "*.pyc" -o -name "*.pyo" \) -print0)
if (( ${#_pyc_files[@]} > 0 )); then
  printf '%s\0' "${_pyc_files[@]}" | xargs -0r rm -f --
  echo "      Removed ${#_pyc_files[@]} bytecode file$( (( ${#_pyc_files[@]} == 1 )) && echo '' || echo 's')."
else
  echo "      No *.pyc/*.pyo files found."
fi

echo "🏁  Cleanup complete."
