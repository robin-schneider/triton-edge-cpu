#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_docker
"${PROJECT_ROOT}/scripts/check-source-lock.sh"
docker build -f "${PROJECT_ROOT}/Dockerfile.python" -t "${ARTIFACT_IMAGE}" \
  --build-arg "PYTHON_BACKEND_COMMIT=${PYTHON_BACKEND_COMMIT}" \
  --build-arg "TRITON_GIT_REF=${TRITON_GIT_REF}" \
  --build-arg "BUILD_JOBS=${BUILD_JOBS}" "${PROJECT_ROOT}"
