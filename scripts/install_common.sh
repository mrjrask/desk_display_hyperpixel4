#!/usr/bin/env bash
set -euo pipefail

EXPECTED_CODENAME="${EXPECTED_CODENAME:-}"

INSTALL_USER="${INSTALL_USER:-pi}"
INSTALL_DIR="${INSTALL_DIR:-/home/${INSTALL_USER}/desk_display_hyperpixel4}"
VENV_PATH="${VENV_PATH:-${INSTALL_DIR}/venv}"
SERVICE_NAME="desk_display.service"
PYTHON_BIN="${PYTHON_BIN:-python3}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${EXPECTED_CODENAME}" ]]; then
  echo "EXPECTED_CODENAME is not set. Source this script from an installer wrapper." >&2
  exit 1
fi

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

check_os() {
  if [[ ! -f /etc/os-release ]]; then
    echo "/etc/os-release not found; cannot detect OS." >&2
    exit 1
  fi

  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${VERSION_CODENAME:-}" != "${EXPECTED_CODENAME}" ]]; then
    echo "This installer is for ${EXPECTED_CODENAME}, but detected '${VERSION_CODENAME:-unknown}'." >&2
    exit 1
  fi
}

install_apt_packages() {
  local shared_packages=(
    python3-venv python3-pip python3-dev python3-opencv
    build-essential libjpeg-dev libopenblas0 libopenblas-dev
    libopenjp2-7-dev libcairo2-dev libpango1.0-dev liblgpio-dev
    libffi-dev network-manager wireless-tools i2c-tools
    fonts-dejavu-core fonts-noto-color-emoji libgl1 libx264-dev ffmpeg git libdrm2 rsync swig
  )

  local codename_packages=()
  case "${EXPECTED_CODENAME}" in
    bookworm)
      codename_packages+=(
        libgdk-pixbuf2.0-dev
        libatlas-base-dev
        libegl1-mesa
        libgles2-mesa
        libtiff5-dev
      )
      ;;
    trixie)
      codename_packages+=(
        libgdk-pixbuf-2.0-dev
        libatlas3-base
        libegl1
        libgles2
        libtiff-dev
      )
      ;;
    *)
      echo "Unsupported codename '${EXPECTED_CODENAME}' for package selection." >&2
      exit 1
      ;;
  esac

  ${SUDO} apt-get update
  ${SUDO} apt-get install -y "${shared_packages[@]}" "${codename_packages[@]}"
}

sync_repository() {
  mkdir -p "${INSTALL_DIR}"
  rsync -a --delete --exclude='.git' --exclude='venv' --exclude='__pycache__' \
    "${REPO_DIR}/" "${INSTALL_DIR}/"
  ${SUDO} chown -R "${INSTALL_USER}:${INSTALL_USER}" "${INSTALL_DIR}"
}

create_virtualenv() {
  run_as_user "${PYTHON_BIN}" -m venv "${VENV_PATH}"
  run_as_user "${VENV_PATH}/bin/pip" install --upgrade pip wheel
  # Ensure editable requirements resolve relative to the repository root.
  run_as_user bash -lc "cd '${INSTALL_DIR}' && '${VENV_PATH}/bin/pip' install -r requirements.txt"
}

prepare_scripts() {
  ${SUDO} chmod +x "${INSTALL_DIR}/cleanup.sh"
  ${SUDO} chmod +x "${INSTALL_DIR}/reset_screenshots.sh"
  ${SUDO} chmod +x "${INSTALL_DIR}/scripts/wait_and_export_display_env.sh"
}

install_service() {
  cat <<SERVICE | ${SUDO} tee /etc/systemd/system/${SERVICE_NAME} >/dev/null
[Unit]
Description=Desk Display (user) - main
After=graphical-session.target network-online.target
Wants=graphical-session.target

[Service]
User=${INSTALL_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=DISPLAY_PROFILE=hyperpixel4_square
EnvironmentFile=-${INSTALL_DIR}/.env
EnvironmentFile=-/run/user/%U/desk_display.env
Environment=INSIDE_SENSOR_I2C_BUS=15
SupplementaryGroups=video render input gpio i2c spi
ExecStartPre=${INSTALL_DIR}/scripts/wait_and_export_display_env.sh
ExecStart=${VENV_PATH}/bin/python ${INSTALL_DIR}/main.py
ExecStop=/bin/bash -lc '${INSTALL_DIR}/cleanup.sh'
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
SERVICE

  ${SUDO} systemctl daemon-reload
  ${SUDO} systemctl enable "${SERVICE_NAME}"
  ${SUDO} systemctl restart "${SERVICE_NAME}"
}

print_summary() {
  cat <<SUMMARY
Installation complete for ${EXPECTED_CODENAME}.
- Repository location: ${INSTALL_DIR}
- Virtual environment: ${VENV_PATH}
- Service: ${SERVICE_NAME} (enabled and started)

Check logs with: sudo journalctl -u ${SERVICE_NAME} -f
SUMMARY
}

run_install() {
  check_os
  require_user
  install_apt_packages
  sync_repository
  create_virtualenv
  prepare_scripts
  install_service
  print_summary
}
