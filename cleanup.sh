#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# Ensure Unix line endings and executable bit:
#   sed -i 's/\r$//' cleanup.sh && chmod +x cleanup.sh

echo "⏱  Running cleanup at $(date +%Y%m%d_%H%M%S)…"

# Work from the repo root (script directory)
dir="$(cd -- "$(dirname "$0")" && pwd)"
cd "$dir"

# Defaults (can be overridden via env)
SCREENSHOTS_DIR="${SCREENSHOTS_DIR:-${dir}/screenshots}"
ARCHIVE_ROOT="${ARCHIVE_ROOT:-${dir}/screenshot_archive}"
ARCHIVE_DATED_DIR="${ARCHIVE_DATED_DIR:-${ARCHIVE_ROOT}/dated_folders}"
ARCHIVE_DEFAULT_FOLDER="${ARCHIVE_DEFAULT_FOLDER:-_unsorted}"

timestamp="$(date +%Y%m%d_%H%M%S)"
day="$(date +%Y%m%d)"
batch="${timestamp}"

# --- 1) Clear the display before touching the filesystem (but only when safe) ---
echo "    → Clearing display…"

# We skip display clearing if running under Wayland without an X11 session.
if [[ -n "${WAYLAND_DISPLAY:-}" && -z "${DISPLAY:-}" ]]; then
  echo "      Skipped (Wayland session without X11: no safe GL context for pygame)."
else
  # Try to clear using your utils.Display; fail soft.
  python3 - <<'PY'
import logging
import os
logging.basicConfig(level=logging.INFO, format="      %(message)s")

# Be quiet about pygame's banner
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# If DISPLAY is unset and we are not in Wayland, try KMSDRM as a best-effort.
# (If this doesn't work in your environment, we still fail soft below.)
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")

try:
    from utils import Display, clear_display  # your project utilities
except Exception as exc:  # pragma: no cover
    logging.warning("Display cleanup skipped: import failed: %s", exc)
else:
    try:
        # Defensive: ensure a best-effort init/quit doesn’t crash the interpreter.
        d = Display()
        clear_display(d)
        try:
            import pygame
            try:
                pygame.display.flip()
            except Exception:
                pass
            try:
                pygame.display.quit()
            except Exception:
                pass
            try:
                pygame.quit()
            except Exception:
                pass
        except Exception:
            pass
        logging.info("Display cleared.")
    except Exception as exc:  # pragma: no cover
        logging.warning("Display cleanup failed (soft): %s", exc)
PY
fi

# --- 2) Archive leftover screenshots/videos to a dated, per-screen folder ---
if [[ -d "${SCREENSHOTS_DIR}" ]]; then
  # Build list of leftover media (png/jpg/mp4/avi) under screenshots/
  # Preserve ordering; handle spaces with -print0.
  mapfile -d '' -t leftover_files < <(
    find "${SCREENSHOTS_DIR}" -type f \
      \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \
         -o -iname '*.mp4' -o -iname '*.avi' \) -print0 | sort -z
  )
else
  leftover_files=()
fi

if (( ${#leftover_files[@]} > 0 )); then
  echo "    → Archiving leftover screenshots/videos to screenshot_archive/dated_folders/<screen>/${day}/cleanup_${batch}…"
  for src in "${leftover_files[@]}"; do
    # Determine screen folder by first path segment under screenshots/
    # e.g., screenshots/bulls/… → screen_folder="bulls"
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

    dest_dir="${ARCHIVE_DATED_DIR}/${screen_folder}/${day}/cleanup_${batch}"
    dest="${dest_dir}/${remainder}"
    mkdir -p "$(dirname "${dest}")"
    mv -f "${src}" "${dest}"
  done

  # Clean up any empty dirs left behind under screenshots/
  if [[ -d "${SCREENSHOTS_DIR}" ]]; then
    find "${SCREENSHOTS_DIR}" -type d -empty -delete
  fi
else
  echo "    → No leftover screenshots/videos to archive."
fi

echo "🏁  Cleanup complete."
