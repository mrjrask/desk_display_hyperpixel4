#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[gate] $*"
}

warn() {
  echo "[gate] $*" >&2
}

die() {
  warn "$1"
  exit 1
}

USER_ID=$(id -u)

FORCE_X11=false
case "${DESK_DISPLAY_FORCE_X11:-0}" in
  1|true|TRUE|yes|on)
    FORCE_X11=true
    ;;
esac

# Try to locate the runtime directory for the session that owns the display.
detect_runtime_dir() {
  if [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -d "${XDG_RUNTIME_DIR}" ]; then
    echo "${XDG_RUNTIME_DIR}"
    return 0
  fi

  if command -v loginctl >/dev/null 2>&1; then
    local session runtime type active best_runtime
    # Prefer active graphical sessions (Wayland/X11) on seat0.
    while IFS=' ' read -r session _ _ seat _; do
      [ -z "${session}" ] && continue
      runtime=$(loginctl show-session "${session}" -p RuntimePath --value 2>/dev/null || true)
      type=$(loginctl show-session "${session}" -p Type --value 2>/dev/null || true)
      active=$(loginctl show-session "${session}" -p Active --value 2>/dev/null || true)
      if [ -n "${runtime}" ] && [ -d "${runtime}" ]; then
        if [ "${active}" = "yes" ] && { [ "${type}" = "wayland" ] || [ "${type}" = "x11" ]; }; then
          echo "${runtime}"
          return 0
        fi
        if [ -z "${best_runtime:-}" ] && { [ "${type}" = "wayland" ] || [ "${type}" = "x11" ] || [ "${seat}" = "seat0" ]; }; then
          best_runtime="${runtime}"
        fi
        if [ -z "${best_runtime:-}" ]; then
          best_runtime="${runtime}"
        fi
      fi
    done < <(loginctl list-sessions --no-legend 2>/dev/null)

    if [ -n "${best_runtime:-}" ]; then
      echo "${best_runtime}"
      return 0
    fi
  fi

  echo "/run/user/${USER_ID}"
}

RUNTIME_DIR=$(detect_runtime_dir)
log "Candidate runtime dir: ${RUNTIME_DIR}"

# Wait for the runtime directory to become available if systemd-logind is still starting up.
if [ ! -d "${RUNTIME_DIR}" ]; then
  log "Waiting for runtime dir to appear…"
  for _ in {1..120}; do
    if [ -d "${RUNTIME_DIR}" ]; then
      break
    fi
    sleep 0.5
  done
fi

if [ ! -d "${RUNTIME_DIR}" ]; then
  if [ "${RUNTIME_DIR}" = "/run/user/${USER_ID}" ]; then
    log "Creating runtime dir for service user (${RUNTIME_DIR})."
    mkdir -p "${RUNTIME_DIR}"
    chmod 700 "${RUNTIME_DIR}"
  else
    die "Runtime dir ${RUNTIME_DIR} never appeared."
  fi
fi

if [ ! -w "${RUNTIME_DIR}" ]; then
  die "Runtime dir ${RUNTIME_DIR} is not writable by $(id -un)."
fi

ENV_FILE="${RUNTIME_DIR}/desk_display.env"
OLD_UMASK=$(umask)
umask 077
TMP_ENV=$(mktemp "${ENV_FILE}.XXXXXX")
umask "${OLD_UMASK}"
trap 'rm -f "${TMP_ENV}"' EXIT

log "Writing environment to ${TMP_ENV}"

# --- Find an available Wayland socket (wayland-0, wayland-1, …) ---
WAYLAND_DISPLAY=""
if [ "${FORCE_X11}" = true ]; then
  log "DESK_DISPLAY_FORCE_X11 requested; skipping Wayland probe."
else
  log "Searching for Wayland socket…"
  for _ in {1..120}; do
    SOCKET=$(ls "${RUNTIME_DIR}"/wayland-* 2>/dev/null | head -n1 || true)
    if [ -n "${SOCKET}" ] && [ -S "${SOCKET}" ]; then
      WAYLAND_DISPLAY=$(basename "${SOCKET}")
      log "Found ${SOCKET}"
      break
    fi
    sleep 0.5
  done

  if [ -z "${WAYLAND_DISPLAY}" ]; then
    warn "No Wayland socket found, will try X11 fallback…"
  fi
fi

# --- Check for a connected DRM connector (HyperPixel is usually DPI-1) ---
log "Checking DRM connector status…"
CONNECTED="no"
if compgen -G "/sys/class/drm/card*-*/status" > /dev/null; then
  for s in /sys/class/drm/card*-*/status; do
    name="$(basename "$(dirname "$s")")"   # e.g. card0-DPI-1
    status="$(cat "$s" 2>/dev/null || echo unknown)"
    log "${name} => ${status}"
    if [ "${status}" = "connected" ]; then
      CONNECTED="yes"
    fi
  done
fi

if [ "${CONNECTED}" != "yes" ]; then
  log "No DRM connector 'connected' yet, waiting up to 30s…"
  for _ in {1..60}; do
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
  die "Gave up waiting for a connected DRM display."
fi

# Determine the owning user so we can export XAUTHORITY for X11 sessions if needed.
RUNTIME_UID=$(stat -c '%u' "${RUNTIME_DIR}")
RUNTIME_USER=$(getent passwd "${RUNTIME_UID}" | cut -d: -f1)
RUNTIME_HOME=$(getent passwd "${RUNTIME_UID}" | cut -d: -f6)
if [ -n "${RUNTIME_USER}" ]; then
  log "Runtime owner: ${RUNTIME_USER} (uid ${RUNTIME_UID})"
else
  log "Runtime owner uid: ${RUNTIME_UID}"
fi

SDL_DRIVER=""
DISPLAY_VALUE="${DISPLAY:-}"
XAUTHORITY_VALUE=""

if [ -n "${WAYLAND_DISPLAY}" ]; then
  SDL_DRIVER="wayland"
  DISPLAY_VALUE="${DISPLAY_VALUE:-:0}"
else
  log "Checking for X11 socket…"
  for _ in {1..120}; do
    if [ -S /tmp/.X11-unix/X0 ]; then
      DISPLAY_VALUE=":0"
      SDL_DRIVER="x11"
      log "Found /tmp/.X11-unix/X0"
      break
    fi
    sleep 0.5
  done

  if [ -z "${SDL_DRIVER}" ]; then
    die "No Wayland or X11 display socket became available."
  fi

  if [ -n "${RUNTIME_HOME}" ] && [ -f "${RUNTIME_HOME}/.Xauthority" ]; then
    XAUTHORITY_VALUE="${RUNTIME_HOME}/.Xauthority"
  fi
fi

if [ -z "${DISPLAY_VALUE}" ]; then
  die "DISPLAY value could not be determined."
fi

DBUS_ADDRESS=""
if [ -S "${RUNTIME_DIR}/bus" ]; then
  DBUS_ADDRESS="unix:path=${RUNTIME_DIR}/bus"
fi

{
  echo "XDG_RUNTIME_DIR=${RUNTIME_DIR}"
  if [ -n "${WAYLAND_DISPLAY}" ]; then
    echo "WAYLAND_DISPLAY=${WAYLAND_DISPLAY}"
  fi
  echo "DISPLAY=${DISPLAY_VALUE}"
  if [ -n "${SDL_DRIVER}" ]; then
    echo "SDL_VIDEODRIVER=${SDL_DRIVER}"
  fi
  if [ -n "${XAUTHORITY_VALUE}" ]; then
    echo "XAUTHORITY=${XAUTHORITY_VALUE}"
  fi
  if [ -n "${DBUS_ADDRESS}" ]; then
    echo "DBUS_SESSION_BUS_ADDRESS=${DBUS_ADDRESS}"
  fi
  echo "SDL_AUDIODRIVER=pulse"
} > "${TMP_ENV}"

mv "${TMP_ENV}" "${ENV_FILE}"
trap - EXIT
log "Wrote env to ${ENV_FILE}:"
cat "${ENV_FILE}"
