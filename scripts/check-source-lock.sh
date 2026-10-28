#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
assert_source_lock
python3 "${PROJECT_ROOT}/scripts/inputs.py" --verify
python3 "${PROJECT_ROOT}/scripts/dependencies.py" check
