#!/usr/bin/env bash
set -euo pipefail

EXPECTED_CODENAME=bookworm
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install_common.sh"

run_install
