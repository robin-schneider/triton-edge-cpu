#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_docker
tooling_run python3 "${PROJECT_ROOT}/scripts/image-size.py" "${TRITON_IMAGE}" \
  "${SIZE_OUTPUT_DIR:-${PROJECT_ROOT}/artifacts/${TRITON_CONTAINER_VERSION}}"
