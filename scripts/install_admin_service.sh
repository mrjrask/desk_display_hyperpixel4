#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/admin_service_common.sh"

require_user
sync_repository
create_virtualenv
install_admin_service
print_install_summary
