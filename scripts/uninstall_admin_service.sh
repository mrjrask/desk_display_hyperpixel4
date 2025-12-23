#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/admin_service_common.sh"

uninstall_admin_service

echo "Removed ${SERVICE_NAME}. Repository and virtualenv remain at ${INSTALL_DIR}."
