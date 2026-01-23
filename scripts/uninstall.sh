#!/usr/bin/env bash
set -euo pipefail

INSTALL_USER="${INSTALL_USER:-pi}"
INSTALL_DIR="${INSTALL_DIR:-/home/${INSTALL_USER}/desk_display_hyperpixel4}"
SERVICE_NAME="${SERVICE_NAME:-desk_display.service}"
REMOVE_INSTALL_DIR="${REMOVE_INSTALL_DIR:-0}"

SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

if [[ $(id -u) -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

remove_service() {
  ${SUDO} systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
  ${SUDO} systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
  if [[ -f "${SERVICE_PATH}" ]]; then
    ${SUDO} rm -f "${SERVICE_PATH}"
    ${SUDO} systemctl daemon-reload
    ${SUDO} systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true
  fi
}

remove_install_dir() {
  if [[ "${REMOVE_INSTALL_DIR}" == "1" ]]; then
    ${SUDO} rm -rf "${INSTALL_DIR}"
  fi
}

print_summary() {
  cat <<SUMMARY
Uninstall complete.
- Service: ${SERVICE_NAME} (stopped and removed)
- Install dir: ${INSTALL_DIR} $(if [[ "${REMOVE_INSTALL_DIR}" == "1" ]]; then echo "(deleted)"; else echo "(kept)"; fi)
SUMMARY
}

remove_service
remove_install_dir
print_summary
