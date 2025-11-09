#!/usr/bin/env bash
set -euo pipefail

# Sensible defaults for Raspberry Pi OS Bookworm + Wayland
: "${XDG_RUNTIME_DIR:="/run/user/$(id -u)"}"
: "${WAYLAND_DISPLAY:="wayland-0"}"

echo "[wait_for_display] Using XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR}"
echo "[wait_for_display] Waiting for Wayland socket ${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}…"

# Wait for the Wayland compositor socket
for i in {1..60}; do
  if [ -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" ]; then
    echo "[wait_for_display] Wayland socket is ready."
    break
  fi
  sleep 0.5
  if [ $i -eq 60 ]; then
    echo "[wait_for_display] Wayland socket not found in time." >&2
    exit 1
  fi
done

# Also ensure at least one connected DRM connector exists
echo "[wait_for_display] Checking DRM connectors…"
if compgen -G "/sys/class/drm/card*-*/status" > /dev/null; then
  for s in /sys/class/drm/card*-*/status; do
    if [ "$(cat "$s" 2>/dev/null || echo unknown)" = "connected" ]; then
      echo "[wait_for_display] DRM connector $(basename "$(dirname "$s")") is connected."
      exit 0
    fi
  done
  echo "[wait_for_display] No DRM connector shows as 'connected' yet. Waiting up to 30s…"
  for i in {1..60}; do
    for s in /sys/class/drm/card*-*/status; do
      if [ "$(cat "$s" 2>/dev/null || echo unknown)" = "connected" ]; then
        echo "[wait_for_display] DRM connector $(basename "$(dirname "$s")") is connected."
        exit 0
      fi
    done
    sleep 0.5
  done
  echo "[wait_for_display] Gave up waiting for a connected DRM display." >&2
  exit 1
else
  # Older stacks might not expose per-connector status; don't hard-fail.
  echo "[wait_for_display] No DRM status files found; continuing."
fi
