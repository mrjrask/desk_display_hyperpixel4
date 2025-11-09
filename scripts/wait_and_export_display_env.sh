#!/usr/bin/env bash
set -euo pipefail

USER_ID=$(id -u)
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${USER_ID}}"
ENV_FILE="${RUNTIME_DIR}/desk_display.env"

mkdir -p "${RUNTIME_DIR}"
: > "${ENV_FILE}"

echo "[gate] RUNTIME_DIR=${RUNTIME_DIR}"

# --- Find an available Wayland socket (wayland-0, wayland-1, …) ---
echo "[gate] Searching for Wayland socket…"
for i in {1..120}; do
  SOCKET=$(ls "${RUNTIME_DIR}"/wayland-* 2>/dev/null | head -n1 || true)
  if [ -n "${SOCKET}" ] && [ -S "${SOCKET}" ]; then
    WAYLAND_DISPLAY=$(basename "${SOCKET}")
    echo "[gate] Found ${SOCKET}"
    break
  fi
  sleep 0.5
done

if [ -z "${SOCKET:-}" ]; then
  echo "[gate] No Wayland socket found in time." >&2
  exit 1
fi

# --- Check for a connected DRM connector (HyperPixel is usually DPI-1) ---
echo "[gate] Checking DRM connector status…"
CONNECTED="no"
if compgen -G "/sys/class/drm/card*-*/status" > /dev/null; then
  for s in /sys/class/drm/card*-*/status; do
    name="$(basename "$(dirname "$s")")"   # e.g. card0-DPI-1
    status="$(cat "$s" 2>/dev/null || echo unknown)"
    echo "[gate] ${name} => ${status}"
    if [ "${status}" = "connected" ]; then
      CONNECTED="yes"
    fi
  done
fi

if [ "${CONNECTED}" != "yes" ]; then
  echo "[gate] No DRM connector 'connected' yet, waiting up to 30s…"
  for i in {1..60}; do
    for s in /sys/class/drm/card*-*/status; do
      if [ "$(cat "$s" 2>/dev/null || echo unknown)" = "connected" ]; then
        CONNECTED="yes"
        break 2
      fi
    done
    sleep 0.5
  done
fi

if [ "${CONNECTED}" != "yes" ]; then
  echo "[gate] Gave up waiting for a connected DRM display." >&2
  exit 1
fi

# --- Export env for the service via a file it can EnvironmentFile= ---
{
  echo "XDG_RUNTIME_DIR=${RUNTIME_DIR}"
  echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY}"
  # Keep X11 around in case toolkits probe it
  echo "DISPLAY=:0"
  # Prefer Wayland for SDL/pygame on Bookworm
  echo "SDL_VIDEODRIVER=wayland"
  echo "SDL_AUDIODRIVER=pulse"
} >> "${ENV_FILE}"

echo "[gate] Wrote env to ${ENV_FILE}:"
cat "${ENV_FILE}"
