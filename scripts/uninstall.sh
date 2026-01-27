#!/usr/bin/env bash
set -euo pipefail

INSTALL_USER="${INSTALL_USER:-pi}"
INSTALL_DIR="${INSTALL_DIR:-/home/${INSTALL_USER}/desk_display_hyperpixel4}"
VENV_PATH="${VENV_PATH:-${INSTALL_DIR}/venv}"
SERVICE_NAME="${SERVICE_NAME:-desk_display.service}"
REMOVE_INSTALL_DIR="${REMOVE_INSTALL_DIR:-0}"
KEEP_VENV="${KEEP_VENV:-0}"

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
    if [[ "${KEEP_VENV}" == "1" && -d "${VENV_PATH}" && "${VENV_PATH}" == "${INSTALL_DIR}/"* ]]; then
      local venv_name
      venv_name="$(basename "${VENV_PATH}")"
      ${SUDO} find "${INSTALL_DIR}" -mindepth 1 -maxdepth 1 ! -name "${venv_name}" -exec rm -rf {} +
    else
      ${SUDO} rm -rf "${INSTALL_DIR}"
    fi
  fi
}

remove_venv() {
  if [[ "${KEEP_VENV}" == "0" && -d "${VENV_PATH}" ]]; then
    ${SUDO} rm -rf "${VENV_PATH}"
  fi
}

prompt_keep_venv() {
  if [[ -d "${VENV_PATH}" ]]; then
    local response
    read -r -p "Keep virtual environment at ${VENV_PATH}? [y/N] " response
    if [[ "${response}" =~ ^[Yy]$ ]]; then
      KEEP_VENV=1
    fi
  fi
}

print_summary() {
  cat <<SUMMARY
Uninstall complete.
- Service: ${SERVICE_NAME} (stopped and removed)
- Install dir: ${INSTALL_DIR} $(if [[ "${REMOVE_INSTALL_DIR}" == "1" ]]; then if [[ "${KEEP_VENV}" == "1" ]]; then echo "(partially deleted; venv kept)"; else echo "(deleted)"; fi else echo "(kept)"; fi)
- Virtual environment: ${VENV_PATH} $(if [[ "${KEEP_VENV}" == "1" ]]; then echo "(kept)"; else echo "(removed)"; fi)
SUMMARY
}

remove_service
prompt_keep_venv
remove_install_dir
remove_venv
print_summary
