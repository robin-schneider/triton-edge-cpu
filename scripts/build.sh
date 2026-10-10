#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_docker
"${PROJECT_ROOT}/scripts/bootstrap.sh"

echo "Building ${TRITON_IMAGE} from ${TRITON_SOURCE_COMMIT} with ${BUILD_JOBS} jobs"
"${PROJECT_ROOT}/scripts/generate.sh"
if [[ "${1:-}" == --reuse-artifacts ]]; then
  docker image inspect tritonserver:latest tritonserver_buildbase:latest >/dev/null
  echo 'Reusing existing core/framework artifacts; compiling Python from its pinned source.'
elif [[ $# == 0 ]]; then
  tooling_run bash "${GENERATED_DIR}/docker_build"
else
  echo 'Usage: scripts/build.sh [--reuse-artifacts]' >&2
  exit 2
fi
"${PROJECT_ROOT}/scripts/build-python.sh"

"${PROJECT_ROOT}/scripts/assemble.sh" --tag "${TRITON_IMAGE}"
tooling_run docker image inspect "${TRITON_IMAGE}" \
  --format 'built {{.Id}} ({{.Size}} bytes)'
echo "Built ${TRITON_IMAGE}"
