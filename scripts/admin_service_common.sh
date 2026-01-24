#!/usr/bin/env bash
set -euo pipefail

INSTALL_USER="${INSTALL_USER:-pi}"
INSTALL_DIR="${INSTALL_DIR:-/home/${INSTALL_USER}/desk_display_hyperpixel4}"
VENV_PATH="${VENV_PATH:-${INSTALL_DIR}/venv}"
SERVICE_NAME="${SERVICE_NAME:-desk_display_admin.service}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ADMIN_HOST="${ADMIN_HOST:-0.0.0.0}"
ADMIN_PORT="${ADMIN_PORT:-5001}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

if [[ $(id -u) -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

require_user() {
  if ! id -u "${INSTALL_USER}" >/dev/null 2>&1; then
    echo "The target user '${INSTALL_USER}' does not exist. Create it or override INSTALL_USER." >&2
    exit 1
  fi
}

run_as_user() {
  if [[ "$(id -un)" == "${INSTALL_USER}" ]]; then
    "$@"
  else
    ${SUDO} -u "${INSTALL_USER}" "$@"
  fi
}

sync_repository() {
  mkdir -p "${INSTALL_DIR}"
  rsync -a --delete --exclude='.git' --exclude='venv' --exclude='__pycache__' \
    "${REPO_DIR}/" "${INSTALL_DIR}/"
  ${SUDO} chown -R "${INSTALL_USER}:${INSTALL_USER}" "${INSTALL_DIR}"
}

create_virtualenv() {
  if [[ -d "${VENV_PATH}" && -x "${VENV_PATH}/bin/python" ]]; then
    echo "Virtual environment already exists at ${VENV_PATH}; reusing it."
  else
    run_as_user "${PYTHON_BIN}" -m venv "${VENV_PATH}"
  fi
  run_as_user "${VENV_PATH}/bin/pip" install --upgrade pip wheel
  run_as_user bash -lc "cd '${INSTALL_DIR}' && '${VENV_PATH}/bin/pip' install -r requirements.txt"
}

write_service_unit() {
  cat <<SERVICE | ${SUDO} tee "${SERVICE_PATH}" >/dev/null
[Unit]
Description=Desk Display Admin (user)
After=network-online.target
Wants=network-online.target

[Service]
User=${INSTALL_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=ADMIN_HOST=${ADMIN_HOST}
Environment=ADMIN_PORT=${ADMIN_PORT}
EnvironmentFile=-${INSTALL_DIR}/.env
ExecStart=${VENV_PATH}/bin/python ${INSTALL_DIR}/admin.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE

  ${SUDO} systemctl daemon-reload
  ${SUDO} systemctl enable "${SERVICE_NAME}"
}

restart_admin_service() {
  ${SUDO} systemctl restart "${SERVICE_NAME}"
}

install_admin_service() {
  write_service_unit
  restart_admin_service
}

uninstall_admin_service() {
  ${SUDO} systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
  ${SUDO} systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
  if [[ -f "${SERVICE_PATH}" ]]; then
    ${SUDO} rm -f "${SERVICE_PATH}"
    ${SUDO} systemctl daemon-reload
    ${SUDO} systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true
  fi
}

print_install_summary() {
  cat <<SUMMARY
Admin service installed.
- Repository location: ${INSTALL_DIR}
- Virtual environment: ${VENV_PATH}
- Service: ${SERVICE_NAME} (enabled and started)
- Admin host/port: ${ADMIN_HOST}:${ADMIN_PORT}

Check logs with: sudo journalctl -u ${SERVICE_NAME} -f
SUMMARY
}
